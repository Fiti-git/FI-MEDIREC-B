import os
import json
from background_task import background
from django.conf import settings
from django.utils import timezone
from django.db import transaction
from pdfminer.high_level import extract_text
from google import genai
from google.genai import types
from django.apps import apps

# 🔑 Replace this with your actual Gemini API key
GEMINI_API_KEY = "AIzaSyBBqnwzsmqlyyDsLmb-vGoCgYaRB3FID7U"


@background(schedule=0)
def extract_and_analyze(uploaded_document_id):
    # Dynamically get models to avoid double registration
    UploadedDocument = apps.get_model("document", "UploadedDocument")
    ExtractedText = apps.get_model("document", "ExtractedText")

    try:
        uploaded_document = UploadedDocument.objects.get(id=uploaded_document_id)

        # Update extraction start status
        uploaded_document.extraction_status = "in_progress"
        uploaded_document.extraction_started_at = timezone.now()
        uploaded_document.extraction_error = None
        uploaded_document.save(
            update_fields=["extraction_status", "extraction_started_at", "extraction_error"]
        )
        print(f"[TASK] Extraction started for document ID {uploaded_document_id}")

        pdf_path = uploaded_document.file.path
        print(f"[TASK] Extracting text from: {pdf_path}")
        text = extract_text(pdf_path)

        # Save text to .txt file
        txt_filename = os.path.splitext(os.path.basename(pdf_path))[0] + ".txt"
        txt_output_dir = os.path.join(settings.MEDIA_ROOT, "texts")
        os.makedirs(txt_output_dir, exist_ok=True)
        txt_output_path = os.path.join(txt_output_dir, txt_filename)

        with open(txt_output_path, "w", encoding="utf-8") as f:
            f.write(text)

        relative_txt_path = os.path.relpath(txt_output_path, settings.MEDIA_ROOT)

        # Save to ExtractedText model within transaction
        with transaction.atomic():
            extracted_text = ExtractedText.objects.create(
                document=uploaded_document, text_file=relative_txt_path
            )
            transaction.on_commit(lambda: print(f"[TASK] ExtractedText committed with ID {extracted_text.id}"))

        # Update extraction finished status
        uploaded_document.extraction_status = "completed"
        uploaded_document.extraction_finished_at = timezone.now()
        uploaded_document.save(
            update_fields=["extraction_status", "extraction_finished_at"]
        )
        print(f"[TASK] Extraction completed for document ID {uploaded_document_id}")

        # Schedule Gemini analysis
        analyze_with_gemini(extracted_text.id, schedule=0)

    except Exception as e:
        try:
            uploaded_document.extraction_status = "error"
            uploaded_document.extraction_error = str(e)
            uploaded_document.save(
                update_fields=["extraction_status", "extraction_error"]
            )
        except Exception as inner_e:
            print(f"[ERROR] Failed to update error status for document {uploaded_document_id}: {inner_e}")
        print(f"[ERROR] extract_and_analyze: {e}")


@background(schedule=0)
def analyze_with_gemini(extracted_text_id):
    ExtractedText = apps.get_model("document", "ExtractedText")
    ProcessedResult = apps.get_model("document", "ProcessedResult")

    try:
        extracted_text_obj = ExtractedText.objects.get(id=extracted_text_id)
        txt_file_path = os.path.join(settings.MEDIA_ROOT, extracted_text_obj.text_file.name)

        with open(txt_file_path, "r", encoding="utf-8") as f:
            medical_text = f.read()

        prompt = f"""
        
You are a highly skilled medical AI assistant specialized in analyzing laboratory reports. 
Your role is to act like a doctor, providing clear explanations and recommendations that patients can easily understand.

Your output must be structured as a single JSON object.

**General JSON Structure Requirements:**

1. **Top-Level Keys**:
    * `patientInformation`: Basic details about the patient.
    * `overallReportSummary`: A concise, easy-to-understand overview of the lab findings.
    * `recommendationsForPatientsReview`: Practical advice for patients including lifestyle, monitoring, and medical guidance.
    * `detailedReports`: A breakdown of test panels and results.
    * `reportMetadata`: Information about the report itself (dates, technicians).

---

### 2. `patientInformation`
* Extract fields like `mrNo`, `name`, `labNo`, `dobAgeGender`, `doctor`, `referredClinic`, `mobileNo`, `encoDate`, `idPassport`, `nationality`.
* If vitals (height, weight, BMI, blood pressure, hand grip, etc.) are available, include them; otherwise mark `"Not available"`.

---

### 3. `overallReportSummary`
* Write in plain, patient-friendly language.
* Highlight both healthy results and areas of concern.
* Example: *“Your cholesterol levels are slightly high, which may increase your risk for heart problems in the future. Your blood sugar is within the normal range, which is good.”*

---

### 4. `recommendationsForPatientsReview`
* Organize recommendations into categories:
    - `heartAndCholesterolHealth`
    - `bloodSugarAndMetabolism`
    - `liverAndKidneyFunction`
    - `vitaminsAndGeneralWellness`
    - `inflammationAndImmunity`
    - `bloodAndHematology`
    - `prostateHealth` (if applicable)

* For each category include:
    - `findings`: Key abnormal or noteworthy results.
    - `lifestyle`: Simple advice (diet, exercise, sleep, stress, hydration, etc.).
    - `monitoring`: What the patient should track (blood pressure, sugar checks, weight, follow-up labs).
    - `medical`: When to consult a doctor, further tests, or treatments to discuss.

* Add a `concludingNote`:  
  "These recommendations are based only on your lab results. For complete care, always discuss these findings with your doctor, who knows your full medical history."

---

### 5. `detailedReports`
* Contain:
    - `testList`: Array of all major test panels.
    - For each panel:
        * `panelName`
        * `overallSummary`: Written in patient-friendly language.
        * `tests`: Array of test objects:
            - `testName`
            - `testResult` (with H/L flags if present)
            - `units`
            - `referenceRange`
            - `status`: "High", "Low", or "Normal"
            - `summary`: Short plain-language explanation of what this means for the patient.
        * If PSA is present, calculate `freePSAPercentage` and explain its meaning in simple terms.

---

### 6. `reportMetadata`
* Include `collectedOn`, `receivedOn`, `authenticatedOn`, `printedOn`, `reprintedOn` formatted as `"DD-MM-YYYY HH:MM:SS"`.
* Include `technicians`: Array with `name`, `role`, and `dhaP`.

---

### 7. Handling Missing Information
* If a value is missing:  
  - For numbers → `null`  
  - For strings → `"Not available in provided data"`  
* For missing groups → use `[]` .

---

### 8. Output Format
* The final output must be a **single well-formed JSON object**.  
* All summaries, explanations, and recommendations must be **clear, supportive, and easy for patients to understand**.


--- BEGIN REPORT ---
{medical_text}
--- END REPORT ---
"""


        parts = [types.Part(text=prompt)]
        contents = [types.Content(role="user", parts=parts)]
        client = genai.Client(api_key=GEMINI_API_KEY)

        response = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=contents,
        )

        try:
            response_json = json.loads(response.text)
        except json.JSONDecodeError:
            response_json = {"raw_response": response.text}

        # Save ProcessedResult in transaction
        with transaction.atomic():
            result_obj = ProcessedResult.objects.create(
                extracted_text=extracted_text_obj, data=response_json
            )
            transaction.on_commit(lambda: print(f"[TASK] ProcessedResult committed for ExtractedText ID {extracted_text_id}"))

        print(f"[TASK] Gemini analysis complete and saved for ExtractedText ID {extracted_text_id}")

    except Exception as e:
        print(f"[ERROR] analyze_with_gemini: {e}")
