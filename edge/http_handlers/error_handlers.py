from flask import Flask, jsonify, request
from werkzeug.exceptions import HTTPException


def register_error_handlers(app: Flask, log_json) -> None:
    """Register shared error handlers for the edge service."""

    @app.errorhandler(413)
    def request_entity_too_large(error):
        correlation_id = getattr(request, 'correlation_id', 'unknown')
        log_json(
            'warn',
            correlation_id,
            'Request too large',
            remote_addr=request.remote_addr,
        )
        return jsonify({'error': 'Request body too large'}), 413

    @app.errorhandler(Exception)
    def handle_exception(exc):
        correlation_id = getattr(request, 'correlation_id', 'unknown')

        if isinstance(exc, HTTPException):
            log_json(
                'warn',
                correlation_id,
                'HTTP exception',
                status_code=exc.code,
                error=str(exc),
            )
            return jsonify({'error': exc.description}), exc.code

        log_json(
            'error',
            correlation_id,
            'Unhandled exception',
            error=str(exc),
            error_type=type(exc).__name__,
        )
        return jsonify({'error': 'Internal server error'}), 500
