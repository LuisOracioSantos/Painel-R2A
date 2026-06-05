from flask import Blueprint


comum_bp = Blueprint(
    "comum",
    __name__,
    static_folder="static",
    static_url_path="/comum/static",
)


__all__ = ["comum_bp"]
