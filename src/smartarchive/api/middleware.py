"""Bound multipart requests before parsing, including unknown-length bodies."""
from tempfile import SpooledTemporaryFile

from starlette.responses import JSONResponse


class UploadLimitMiddleware:
    def __init__(self, app, max_bytes: int, allowed_origins: tuple[str, ...]):
        self.app, self.limit, self.origins = app, max_bytes, allowed_origins

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http' or scope['method'] not in ('POST', 'PUT', 'PATCH'):
            return await self.app(scope, receive, send)
        headers = dict(scope.get('headers', []))
        origin = headers.get(b'origin', b'').decode('latin-1')
        if origin and origin not in self.origins:
            return await JSONResponse({'detail': 'Origin is not allowed'}, status_code=403)(scope, receive, send)
        try:
            length = int(headers.get(b'content-length', b'0'))
            if length < 0:
                raise ValueError
        except ValueError:
            return await JSONResponse({'detail': 'Invalid Content-Length'}, status_code=400)(scope, receive, send)
        if length > self.limit:
            return await JSONResponse({'detail': 'Upload request is too large'}, status_code=413)(scope, receive, send)
        with SpooledTemporaryFile(max_size=1024 * 1024, mode='w+b') as body:
            size = 0
            while True:
                message = await receive()
                if message['type'] == 'http.disconnect':
                    return
                chunk = message.get('body', b'')
                size += len(chunk)
                if size > self.limit:
                    return await JSONResponse({'detail': 'Upload request is too large'}, status_code=413)(scope, receive, send)
                body.write(chunk)
                if not message.get('more_body', False):
                    break
            body.seek(0)

            async def replay():
                chunk = body.read(64 * 1024)
                if chunk:
                    return {'type': 'http.request', 'body': chunk, 'more_body': body.tell() < size}
                return await receive()

            await self.app(scope, replay, send)
