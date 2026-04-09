from datetime import datetime
import base64
from io import BytesIO

import cv2
import numpy as np
import qrcode
from flask import Blueprint, jsonify, request, send_file

from crypto import hash_record, sign, verify
from supabase_client import supabase

attendance_bp = Blueprint("attendance", __name__)


def get_teacher(teacher_id):
    return (
        supabase.table("teachers")
        .select("*")
        .eq("id", str(teacher_id))
        .execute()
    )


def get_teacher_name(teacher_id):
    teacher_response = get_teacher(teacher_id)
    if not teacher_response.data:
        return None

    teacher = teacher_response.data[0]
    return f"{teacher['first_name']} {teacher['last_name']}"


def build_record(teacher_id, action):
    now = datetime.now()
    return {
        "teacher_id": str(teacher_id),
        "date": str(now.date()),
        "time": now.strftime("%H:%M:%S"),
        "action": action,
    }


def log_signed_attendance(teacher_id, action):
    record = build_record(teacher_id, action)
    h = hash_record(record)
    r, s = sign(h)

    response = supabase.table("attendance").insert({
        **record,
        "r": r,
        "s": s,
    }).execute()

    return record, response, (r, s)


def get_last_attendance_action(teacher_id):
    response = (
        supabase.table("attendance")
        .select("action")
        .eq("teacher_id", str(teacher_id))
        .order("date", desc=True)
        .order("time", desc=True)
        .order("id", desc=True)
        .limit(1)
        .execute()
    )
    if response.data:
        return response.data[0]["action"]
    return None


def get_next_scan_action(teacher_id):
    return "OUT" if get_last_attendance_action(teacher_id) == "IN" else "IN"


def decode_qr_from_data_url(data_url):
    if not data_url or "," not in data_url:
        return None

    _, encoded = data_url.split(",", 1)
    image_bytes = base64.b64decode(encoded)
    image_array = np.frombuffer(image_bytes, dtype=np.uint8)
    image = cv2.imdecode(image_array, cv2.IMREAD_COLOR)
    if image is None:
        return None

    detector = cv2.QRCodeDetector()
    decoded_text, _, _ = detector.detectAndDecode(image)
    return decoded_text.strip() if decoded_text else None


def generate_qr_png(payload):
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=10,
        border=4,
    )
    qr.add_data(payload)
    qr.make(fit=True)

    img = qr.make_image(fill_color="black", back_color="white")
    buffer = BytesIO()
    img.save(buffer, format="PNG")
    buffer.seek(0)
    return buffer


@attendance_bp.route("/time", methods=["POST"])
def log_time():
    try:
        data = request.json or {}
        teacher_id = str(data.get("teacher_id", "")).strip()
        action = str(data.get("action", "")).strip().upper()

        if not teacher_id or not action:
            return jsonify({"error": "Please input your ID."}), 400

        if action not in {"IN", "OUT"}:
            return jsonify({"error": "Invalid attendance action."}), 400

        teacher_name = get_teacher_name(teacher_id)
        if not teacher_name:
            return jsonify({"error": "Invalid Teacher ID."}), 400

        _, response, (r, s) = log_signed_attendance(teacher_id, action)
        print("SUPABASE RESPONSE:", response)

        return jsonify({
            "message": f"{teacher_name} recorded for {action}.",
            "signature": [r, s],
            "teacher_name": teacher_name,
            "action": action,
        }), 200
    except Exception as e:
        print("ERROR:", str(e))
        return jsonify({"error": str(e)}), 500


@attendance_bp.route("/scan-time", methods=["POST"])
def scan_time():
    try:
        data = request.json or {}
        teacher_id = str(data.get("teacher_id", "")).strip()

        if not teacher_id:
            return jsonify({"error": "QR code did not contain a teacher ID."}), 400

        teacher_name = get_teacher_name(teacher_id)
        if not teacher_name:
            return jsonify({"error": "Teacher ID from QR is not registered."}), 400

        action = get_next_scan_action(teacher_id)
        _, _, (r, s) = log_signed_attendance(teacher_id, action)

        return jsonify({
            "message": f"{teacher_name} recorded for {action}.",
            "teacher_id": teacher_id,
            "teacher_name": teacher_name,
            "action": action,
            "signature": [r, s],
        }), 200
    except Exception as e:
        print("SCAN ERROR:", str(e))
        return jsonify({"error": str(e)}), 500


@attendance_bp.route("/scan-frame", methods=["POST"])
def scan_frame():
    try:
        data = request.json or {}
        image_data = data.get("image")
        teacher_id = decode_qr_from_data_url(image_data)

        if not teacher_id:
            return jsonify({"teacher_id": None}), 200

        return jsonify({"teacher_id": teacher_id}), 200
    except Exception as e:
        print("FRAME SCAN ERROR:", str(e))
        return jsonify({"error": str(e)}), 500


@attendance_bp.route("/verify", methods=["GET"])
def verify_all():
    try:
        response = supabase.table("attendance").select("*").execute()
        records = response.data
        results = []

        for entry in records:
            record = {
                "teacher_id": entry["teacher_id"],
                "date": entry["date"],
                "time": entry["time"],
                "action": entry["action"],
            }

            try:
                valid = verify(record, entry["r"], entry["s"])
            except Exception as e:
                print("VERIFY ERROR:", e)
                valid = False

            name = get_teacher_name(entry["teacher_id"]) or "Unknown"

            results.append({
                "id": entry["id"],
                "teacher_id": entry["teacher_id"],
                "name": name,
                "date": entry["date"],
                "time": entry["time"],
                "action": entry["action"],
                "valid": valid,
            })

        return jsonify(results), 200
    except Exception as e:
        print("VERIFY ERROR:", str(e))
        return jsonify({"error": str(e)}), 500


@attendance_bp.route("/teachers", methods=["GET"])
def list_teachers():
    try:
        response = supabase.table("teachers").select("*").order("id").execute()
        teachers = [
            {
                "id": str(teacher["id"]),
                "name": f"{teacher['first_name']} {teacher['last_name']}",
            }
            for teacher in response.data
        ]
        return jsonify(teachers), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@attendance_bp.route("/teachers", methods=["POST"])
def create_teacher():
    try:
        data = request.json or {}
        teacher_id = str(data.get("id", "")).strip()
        first_name = str(data.get("first_name", "")).strip()
        last_name = str(data.get("last_name", "")).strip()

        if not teacher_id or not first_name or not last_name:
            return jsonify({"error": "ID, first name, and last name are required."}), 400

        if not teacher_id.isdigit():
            return jsonify({"error": "Teacher ID must be numeric."}), 400

        existing = get_teacher(teacher_id)
        if existing.data:
            return jsonify({"error": "Teacher ID already exists."}), 400

        supabase.table("teachers").insert({
            "id": int(teacher_id),
            "first_name": first_name,
            "last_name": last_name,
        }).execute()

        return jsonify({
            "message": f"{first_name} {last_name} added successfully.",
            "teacher": {
                "id": teacher_id,
                "name": f"{first_name} {last_name}",
            },
        }), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@attendance_bp.route("/teachers/<teacher_id>/qr", methods=["GET"])
def teacher_qr(teacher_id):
    try:
        teacher_name = get_teacher_name(teacher_id)
        if not teacher_name:
            return jsonify({"error": "Invalid Teacher ID."}), 404

        return jsonify({
            "teacher_id": str(teacher_id),
            "name": teacher_name,
            "qr_image_url": f"/teachers/{teacher_id}/qr.png",
            "download_url": f"/teachers/{teacher_id}/qr.png?download=1",
            "filename": f"teacher_{teacher_id}_qr.png",
        }), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@attendance_bp.route("/teachers/<teacher_id>/qr.png", methods=["GET"])
def teacher_qr_png(teacher_id):
    try:
        teacher_name = get_teacher_name(teacher_id)
        if not teacher_name:
            return jsonify({"error": "Invalid Teacher ID."}), 404

        filename = f"teacher_{teacher_id}_qr.png"
        as_attachment = request.args.get("download") == "1"

        return send_file(
            generate_qr_png(str(teacher_id)),
            mimetype="image/png",
            as_attachment=as_attachment,
            download_name=filename,
        )
    except Exception as e:
        return jsonify({"error": str(e)}), 500
