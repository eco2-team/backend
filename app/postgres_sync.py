"""
PostgreSQL Sync Manager

WAL에서 PostgreSQL로 작업 결과 동기화
"""

import json
import logging
from typing import Any, Dict, List, Optional

import asyncpg

from app.wal import WALManager

logger = logging.getLogger(__name__)


class PostgreSQLSyncManager:
    """WAL -> PostgreSQL 동기화 매니저"""

    def __init__(
        self,
        host: str,
        port: int,
        database: str,
        user: str,
        password: str,
        wal_manager: WALManager,
    ):
        """
        PostgreSQL Sync Manager 초기화

        Args:
            host: PostgreSQL 호스트
            port: PostgreSQL 포트
            database: 데이터베이스 이름
            user: 사용자명
            password: 비밀번호
            wal_manager: WAL Manager 인스턴스
        """
        self.host = host
        self.port = port
        self.database = database
        self.user = user
        self.password = password
        self.wal = wal_manager
        self.pool: Optional[asyncpg.Pool] = None

    async def init_pool(self, min_size: int = 5, max_size: int = 20):
        """
        Connection Pool 초기화

        Args:
            min_size: 최소 연결 수
            max_size: 최대 연결 수
        """
        try:
            self.pool = await asyncpg.create_pool(
                host=self.host,
                port=self.port,
                database=self.database,
                user=self.user,
                password=self.password,
                min_size=min_size,
                max_size=max_size,
                command_timeout=60,
            )
            logger.info(f"PostgreSQL connection pool initialized ({min_size}-{max_size})")
        except Exception as e:
            logger.error(f"Failed to initialize PostgreSQL pool: {e}")
            raise

    async def close_pool(self):
        """Connection Pool 종료"""
        if self.pool:
            await self.pool.close()
            logger.info("PostgreSQL connection pool closed")

    async def ensure_tables(self):
        """
        PostgreSQL 테이블 생성 (없으면)

        테이블:
        - task_results: 작업 결과
        - task_history: 작업 히스토리
        """
        if not self.pool:
            raise RuntimeError("Connection pool not initialized")

        async with self.pool.acquire() as conn:
            # task_results 테이블
            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS task_results (
                    task_id TEXT PRIMARY KEY,
                    task_name TEXT NOT NULL,
                    worker_name TEXT NOT NULL,
                    status TEXT NOT NULL,
                    result JSONB,
                    error TEXT,
                    retry_count INTEGER DEFAULT 0,
                    created_at TIMESTAMP NOT NULL,
                    started_at TIMESTAMP,
                    completed_at TIMESTAMP,
                    synced_at TIMESTAMP DEFAULT NOW()
                )
            """
            )

            # task_history 테이블 (로그용)
            await conn.execute(
                """
                CREATE TABLE IF NOT EXISTS task_history (
                    id SERIAL PRIMARY KEY,
                    task_id TEXT NOT NULL,
                    task_name TEXT NOT NULL,
                    worker_name TEXT NOT NULL,
                    status TEXT NOT NULL,
                    result JSONB,
                    error TEXT,
                    retry_count INTEGER DEFAULT 0,
                    created_at TIMESTAMP NOT NULL,
                    started_at TIMESTAMP,
                    completed_at TIMESTAMP,
                    synced_at TIMESTAMP DEFAULT NOW()
                )
            """
            )

            # 인덱스 생성
            await conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_task_results_created_at
                ON task_results(created_at)
            """
            )

            await conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_task_history_task_id
                ON task_history(task_id)
            """
            )

            await conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_task_history_created_at
                ON task_history(created_at)
            """
            )

            logger.info("PostgreSQL tables ensured")

    async def sync_task(self, task: Dict[str, Any]) -> bool:
        """
        단일 작업 동기화

        Args:
            task: WAL에서 가져온 작업 데이터

        Returns:
            성공 여부
        """
        if not self.pool:
            raise RuntimeError("Connection pool not initialized")

        try:
            async with self.pool.acquire() as conn:
                async with conn.transaction():
                    # task_results에 UPSERT
                    await conn.execute(
                        """
                        INSERT INTO task_results (
                            task_id, task_name, worker_name, status,
                            result, error, retry_count,
                            created_at, started_at, completed_at
                        ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
                        ON CONFLICT (task_id) DO UPDATE SET
                            status = EXCLUDED.status,
                            result = EXCLUDED.result,
                            error = EXCLUDED.error,
                            retry_count = EXCLUDED.retry_count,
                            completed_at = EXCLUDED.completed_at,
                            synced_at = NOW()
                    """,
                        task["task_id"],
                        task["task_name"],
                        task["worker_name"],
                        task["status"],
                        task.get("result"),
                        task.get("error"),
                        task.get("retry_count", 0),
                        task["created_at"],
                        task.get("started_at"),
                        task.get("completed_at"),
                    )

                    # task_history에 INSERT (히스토리 로그)
                    await conn.execute(
                        """
                        INSERT INTO task_history (
                            task_id, task_name, worker_name, status,
                            result, error, retry_count,
                            created_at, started_at, completed_at
                        ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
                    """,
                        task["task_id"],
                        task["task_name"],
                        task["worker_name"],
                        task["status"],
                        task.get("result"),
                        task.get("error"),
                        task.get("retry_count", 0),
                        task["created_at"],
                        task.get("started_at"),
                        task.get("completed_at"),
                    )

            logger.debug(f"Task {task['task_id']} synced to PostgreSQL")
            return True

        except Exception as e:
            logger.error(f"Failed to sync task {task['task_id']}: {e}")
            return False

    async def sync_batch(self, limit: int = 100) -> int:
        """
        배치 동기화 (WAL에서 미동기화 작업들 가져와서 동기화)

        Args:
            limit: 배치 크기

        Returns:
            동기화된 작업 수
        """
        # WAL에서 미동기화 작업 조회
        tasks = self.wal.get_unsynced_tasks(limit=limit)

        if not tasks:
            logger.debug("No tasks to sync")
            return 0

        synced_count = 0

        for task in tasks:
            # PostgreSQL 동기화
            success = await self.sync_task(task)

            if success:
                # WAL에 동기화 완료 표시
                self.wal.mark_synced(task["task_id"])
                synced_count += 1
            else:
                # 실패 시 다음 배치에서 재시도
                logger.warning(f"Failed to sync task {task['task_id']}, will retry later")

        logger.info(f"Synced {synced_count}/{len(tasks)} tasks to PostgreSQL")
        return synced_count

    async def force_sync_all(self) -> int:
        """
        모든 미동기화 작업 강제 동기화

        Returns:
            동기화된 작업 수
        """
        logger.info("Force syncing all unsynced tasks...")

        total_synced = 0
        batch_size = 100

        while True:
            synced = await self.sync_batch(limit=batch_size)
            total_synced += synced

            if synced < batch_size:
                # 더 이상 동기화할 작업 없음
                break

        logger.info(f"Force sync completed: {total_synced} tasks synced")
        return total_synced

    async def get_task_result(self, task_id: str) -> Optional[Dict[str, Any]]:
        """
        PostgreSQL에서 작업 결과 조회

        Args:
            task_id: Task ID

        Returns:
            작업 결과 (없으면 None)
        """
        if not self.pool:
            raise RuntimeError("Connection pool not initialized")

        try:
            async with self.pool.acquire() as conn:
                row = await conn.fetchrow(
                    """
                    SELECT * FROM task_results
                    WHERE task_id = $1
                """,
                    task_id,
                )

                if row:
                    return dict(row)
                return None

        except Exception as e:
            logger.error(f"Failed to get task result for {task_id}: {e}")
            return None

    async def get_task_history(self, task_id: str) -> List[Dict[str, Any]]:
        """
        PostgreSQL에서 작업 히스토리 조회

        Args:
            task_id: Task ID

        Returns:
            작업 히스토리 목록
        """
        if not self.pool:
            raise RuntimeError("Connection pool not initialized")

        try:
            async with self.pool.acquire() as conn:
                rows = await conn.fetch(
                    """
                    SELECT * FROM task_history
                    WHERE task_id = $1
                    ORDER BY synced_at DESC
                """,
                    task_id,
                )

                return [dict(row) for row in rows]

        except Exception as e:
            logger.error(f"Failed to get task history for {task_id}: {e}")
            return []

    async def cleanup_old_tasks(self, days: int = 30) -> int:
        """
        오래된 작업 결과 정리

        Args:
            days: 보관 일수

        Returns:
            삭제된 작업 수
        """
        if not self.pool:
            raise RuntimeError("Connection pool not initialized")

        try:
            async with self.pool.acquire() as conn:
                # task_results 정리 (최종 결과만 보관)
                result = await conn.execute(
                    """
                    DELETE FROM task_results
                    WHERE completed_at < NOW() - INTERVAL '%s days'
                """,
                    days,
                )

                deleted_count = int(result.split()[-1])

                logger.info(f"Cleaned up {deleted_count} old task results (> {days} days)")
                return deleted_count

        except Exception as e:
            logger.error(f"Failed to cleanup old tasks: {e}")
            return 0

