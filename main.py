from flask import Flask, request, jsonify
import requests
import tempfile
import os

app = Flask(__name__)

# إعدادات السيرفرات
orthanc_url = "http://orthanc:8042"

orthanc_auth = ('orthanc', 'orthanc')
ohif_viewer_base_url = "http://localhost:8042/ohif/viewer"

def check_orthanc():
    try:
        response = requests.get(orthanc_url, auth=orthanc_auth)
        response.raise_for_status()
        return True
    except requests.exceptions.RequestException:
        return False

@app.route("/upload-dicom-url", methods=["POST"])
def upload_dicom_url():
    if not check_orthanc():
        return jsonify({"error": "Orthanc server is not reachable"}), 500

    data = request.get_json()
    dicom_url = data.get("dicom_url")

    if not dicom_url:
        return jsonify({"error": "Missing 'dicom_url' in request"}), 400

    try:
        # تحميل DICOM مؤقتاً
        response = requests.get(dicom_url, timeout=10)
        response.raise_for_status()
        with tempfile.NamedTemporaryFile(delete=False) as tmp_file:
            tmp_file.write(response.content)
            dicom_file_path = tmp_file.name
    except Exception as e:
        return jsonify({"error": f"Failed to download DICOM file: {str(e)}"}), 400

    try:
        # رفع الملف إلى Orthanc
        with open(dicom_file_path, 'rb') as f:
            headers = {'Content-Type': 'application/dicom'}
            upload_response = requests.post(
                f"{orthanc_url}/instances",
                headers=headers,
                data=f,
                auth=orthanc_auth
            )
            upload_response.raise_for_status()
            upload_data = upload_response.json()

        study_id = upload_data.get("ParentStudy")
        if not study_id:
            return jsonify({"error": "No Study ID returned from Orthanc"}), 500

        # الحصول على StudyInstanceUID
        study_metadata = requests.get(f"{orthanc_url}/studies/{study_id}", auth=orthanc_auth).json()
        study_uid = study_metadata.get("MainDicomTags", {}).get("StudyInstanceUID")
        if not study_uid:
            return jsonify({"error": "StudyInstanceUID not found in metadata"}), 500

        viewer_url = f"{ohif_viewer_base_url}?StudyInstanceUIDs={study_uid}"
        return jsonify({
            "viewer_url": viewer_url,
            "study_uid": study_uid
        })

    except Exception as e:
        return jsonify({"error": f"Processing error: {str(e)}"}), 500

    finally:
        if os.path.exists(dicom_file_path):
            os.remove(dicom_file_path)

if __name__ == "__main__":
    app.run(debug=True, port=5000)
