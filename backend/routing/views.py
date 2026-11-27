import json
from datetime import datetime, timezone
from functools import partial

from django.conf import settings
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from . import providers
from .planner import build_plan

ALLOWED_INTERVALS = (10, 25, 50)


class BadRequest(Exception):
    pass


def _parse_request(request):
    try:
        body = json.loads(request.body or b"{}")
    except json.JSONDecodeError as exc:
        raise BadRequest("Request body must be JSON.") from exc

    origin = str(body.get("origin", "")).strip()
    destination = str(body.get("destination", "")).strip()
    if not origin or not destination:
        raise BadRequest("Origin and destination are required.")

    try:
        departure = datetime.fromisoformat(str(body["departure"]).replace("Z", "+00:00"))
    except (KeyError, ValueError) as exc:
        raise BadRequest("Departure must be an ISO date/time.") from exc
    if departure.tzinfo is None:
        departure = departure.replace(tzinfo=timezone.utc)
    departure = departure.astimezone(timezone.utc)

    try:
        load_lb = float(body.get("load_lb"))
    except (TypeError, ValueError) as exc:
        raise BadRequest("Load weight must be a number.") from exc
    if not 0 <= load_lb <= 150_000:
        raise BadRequest("Load weight must be between 0 and 150,000 lb.")

    interval = int(body.get("interval_miles", 25))
    if interval not in ALLOWED_INTERVALS:
        raise BadRequest(f"Checkpoint interval must be one of {ALLOWED_INTERVALS}.")

    try:
        weather = providers.parse_supplied_weather(body.get("weather", []))
    except (TypeError, ValueError) as exc:
        raise BadRequest("Weather data is not in the expected format.") from exc
    return origin, destination, departure, load_lb, interval, weather


@require_GET
def health(_request):
    return JsonResponse({"status": "ok"})


@csrf_exempt
@require_POST
def plan(request):
    try:
        origin, destination, departure, load_lb, interval, weather = _parse_request(request)
        start = providers.geocode(origin)
        end = providers.geocode(destination)
        fetch = partial(providers.fetch_weather, supplied=weather)
        return JsonResponse(build_plan(start, end, departure, load_lb, interval, fetch=fetch))
    except BadRequest as exc:
        return JsonResponse({"error": str(exc)}, status=400)
    except providers.WeatherRateLimited as exc:
        # Ask the browser to fetch these cells and send the request again.
        needed = {
            "url": settings.OPEN_METEO_URL,
            "params": providers.WEATHER_PARAMS,
            "chunk_size": providers.WEATHER_CHUNK,
            "cells": exc.cells,
        }
        return JsonResponse({"error": str(exc), "weather_needed": needed}, status=503)
    except providers.ProviderError as exc:
        return JsonResponse({"error": str(exc)}, status=exc.status)
