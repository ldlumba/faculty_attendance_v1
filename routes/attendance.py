from flask import Blueprint, request, jsonify
from datetime import datetime
from supabase_client import supabase
from crypto import hash_record, sign, verify

attendance_bp = Blueprint('attendance', __name__)

@attendance_bp.route('/time', methods=['POST'])
def log_time():
    try:
        data = request.json
        teacher_id = data.get('teacher_id')
        action = data.get('action')

        # ✅ VALIDATE INPUT
        if not teacher_id or not action:
            return jsonify({"error": "Please input your ID."}), 400

        # ✅ VALIDATE TEACHER EXISTS
        teacher = supabase.table("teachers") \
            .select("*") \
            .eq("id", teacher_id) \
            .execute()

        if not teacher.data:
            return jsonify({"error": "Invalid Teacher ID."}), 400

        # ✅ CREATE RECORD
        now = datetime.now()

        record = {
            "teacher_id": teacher_id,
            "date": str(now.date()),
            "time": now.strftime("%H:%M:%S"),  # FIXED
            "action": action
        }

        # ✅ SIGN WITH DSA
        h = hash_record(record)
        r, s = sign(h)

        # ✅ STORE IN SUPABASE
        response = supabase.table("attendance").insert({
            **record,
            "r": r,
            "s": s
        }).execute()

        print("SUPABASE RESPONSE:", response)

        return jsonify({
            "message": "Attendance logged",
            "signature": [r, s]
        }), 200

    except Exception as e:
        print("ERROR:", str(e))
        return jsonify({"error": str(e)}), 500


@attendance_bp.route('/verify', methods=['GET'])
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
                "action": entry["action"]
            }

            # ✅ VERIFY SIGNATURE
            try:
                valid = verify(record, entry["r"], entry["s"])
            except Exception as e:
                print("VERIFY ERROR:", e)
                valid = False

            # ✅ GET TEACHER NAME
            teacher_info = supabase.table("teachers") \
                .select("*") \
                .eq("id", entry["teacher_id"]) \
                .execute()

            name = "Unknown"
            if teacher_info.data:
                t = teacher_info.data[0]
                name = f"{t['first_name']} {t['last_name']}"

            # ✅ APPEND RESULT
            results.append({
                "id": entry["id"],
                "teacher_id": entry["teacher_id"],
                "name": name,
                "date": entry["date"],
                "time": entry["time"],
                "action": entry["action"],
                "valid": valid
            })

        return jsonify(results), 200

    except Exception as e:
        print("VERIFY ERROR:", str(e))
        return jsonify({"error": str(e)}), 500