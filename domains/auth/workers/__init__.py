"""Background workers for auth domain.

Workers:
    - init_db: Database schema initialization
    - reset_user_data: Reset auth schema (development only)
    - blacklist_relay: Redis Outbox → RabbitMQ relay
"""
