"""Container entrypoint: Railway runtime PORT and IPv6/private-network support."""
import os
import uvicorn

if __name__ == '__main__':
    default_host = '::' if os.getenv('RAILWAY_ENVIRONMENT_ID') else '0.0.0.0'
    uvicorn.run('backend.platform.api:app', host=os.getenv('BIND_HOST', default_host),
                port=int(os.getenv('PORT', '8000')), proxy_headers=False)
