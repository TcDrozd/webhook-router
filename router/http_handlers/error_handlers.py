from flask import jsonify, request
from werkzeug.exceptions import HTTPException


def register_error_handlers(app, log_json):
    """Attach global error handlers to the Flask app."""

    @app.errorhandler(Exception)
    def handle_exception(exc):  # noqa: ANN001
        correlation_id = request.headers.get('X-Correlation-ID', 'unknown')

        if isinstance(exc, HTTPException):
            log_json('warn', correlation_id, 'HTTP exception',
                     status_code=exc.code,
                     error=str(exc))
            return jsonify({'error': exc.description}), exc.code

        log_json('error', correlation_id, 'Unhandled exception',
                 error=str(exc),
                 error_type=type(exc).__name__)
        return jsonify({'error': 'Internal server error'}), 500
