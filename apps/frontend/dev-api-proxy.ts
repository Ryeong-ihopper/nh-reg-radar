export function developmentApiProxy(target = "http://backend:8000") {
  return {
    "/api": {
      target,
      changeOrigin: true,
    },
  };
}
