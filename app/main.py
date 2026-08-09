"""Flask application entry point."""

from flask import Flask, jsonify, render_template

from app.core.config import settings
from app.extensions import close_db, init_engine
from app.web.auth import csrf_token, load_identity, validate_csrf


def create_app(test_config: dict | None = None) -> Flask:
    app = Flask(__name__, template_folder="templates", static_folder="static")
    app.config.from_mapping(
        APP_NAME=settings.APP_NAME,
        DEBUG=settings.DEBUG,
        DATABASE_URL=settings.DATABASE_URL,
        BACKUP_DIR=settings.BACKUP_DIR,
        SECRET_KEY=settings.SECRET_KEY,
        MAX_CONTENT_LENGTH=256 * 1024 * 1024,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=settings.SESSION_COOKIE_SECURE,
        SESSION_COOKIE_NAME="ficusacc_session",
    )
    if test_config:
        app.config.update(test_config)

    init_engine(app)
    app.teardown_appcontext(close_db)
    app.before_request(load_identity)
    app.before_request(validate_csrf)
    app.jinja_env.globals["csrf_token"] = csrf_token

    from app.web.routes import web

    app.register_blueprint(web)

    @app.get("/health")
    def health_check():
        return jsonify(status="healthy", app=app.config["APP_NAME"])

    @app.errorhandler(400)
    @app.errorhandler(403)
    @app.errorhandler(404)
    @app.errorhandler(500)
    def error_page(error):
        return render_template("errors/error.html", error=error), error.code

    return app


app = create_app()
