import pandas as pd

from m4s_seagrass_qa import SITE_CENTROID, validate_gps, add_qa_columns, _haversine_m


def _gps_frame(lat, lon, precision=5):
    return pd.DataFrame(
        [{
            "_uuid": "test-record",
            "_Local GPS_latitude": lat,
            "_Local GPS_longitude": lon,
            "_Local GPS_precision": precision,
        }]
    )


def test_far_gps_point_is_review_warning_not_polygon_error():
    lat, lon = SITE_CENTROID[0] + 0.1, SITE_CENTROID[1]
    issues = validate_gps(_gps_frame(lat, lon))

    distance_issue = next(issue for issue in issues if "centroid-distance threshold" in issue["message"])
    assert distance_issue["severity"] == "warning"
    assert "Verify coordinates, CRS, and site assignment" in distance_issue["message"]
    assert "does not test polygon containment" in distance_issue["message"]


def test_gps_within_configured_centroid_radius_has_no_distance_finding():
    lat, lon = SITE_CENTROID
    issues = validate_gps(_gps_frame(lat, lon))

    assert not any("centroid-distance threshold" in issue["message"] for issue in issues)


def test_qa_export_marks_centroid_alert_for_review():
    lat, lon = SITE_CENTROID[0] + 0.1, SITE_CENTROID[1]
    raw = _gps_frame(lat, lon)
    issues = pd.DataFrame(validate_gps(raw))
    flagged = add_qa_columns(raw, issues)

    assert flagged.loc[0, "qa_outside_boundary"] == "Review"
    assert "does not test polygon containment" in flagged.loc[0, "Message"]
