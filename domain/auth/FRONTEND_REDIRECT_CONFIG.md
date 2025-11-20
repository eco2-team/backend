# OAuth 리다이렉트 설정

## 환경별 프론트엔드 URL

### Dev/Staging
```
https://frontend-beta-gray-c44lrfj3n1.vercel.app
```

### Prod
```
https://growbin.app (TBD)
```

## 리다이렉트 경로

### 성공 시
```
https://frontend-beta-gray-c44lrfj3n1.vercel.app/
```

### 실패 시
```
https://frontend-beta-gray-c44lrfj3n1.vercel.app/?error=login_failed&message=...
```

## 프론트엔드 구현

### 홈 페이지 (/)
```javascript
useEffect(() => {
  // 로그인 상태 확인
  const checkAuth = async () => {
    try {
      const response = await fetch('https://api.growbin.app/api/v1/auth/me', {
        credentials: 'include'
      });
      
      if (response.ok) {
        const data = await response.json();
        setUser(data.data); // 로그인 상태
      } else {
        setUser(null); // 로그아웃 상태
      }
    } catch (error) {
      setUser(null);
    }
  };
  
  checkAuth();
  
  // URL 쿼리 파라미터 확인
  const params = new URLSearchParams(window.location.search);
  const error = params.get('error');
  
  if (error) {
    showErrorToast('로그인 실패: ' + params.get('message'));
  }
}, []);
```

