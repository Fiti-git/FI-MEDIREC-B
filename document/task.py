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
You are a highly skilled medical AI assistant specialized in analyzing lab reports.
Your task is to meticulously extract and interpret all relevant information from the provided medical lab report.
You must structure your output as a single Darft word document Type.

**General JSON Structure Requirements:**

1.  **Top-Level Keys**: The JSON should have the following main keys:
    *   `patientInformation`: Details about the patient.
    *   `overallReportSummary`: A concise, high-level summary of the entire report.
    *   `recommendationsForDoctorsReview`: Clinical recommendations based on significant findings.
    *   `detailedReports`: A breakdown of all lab tests, grouped by panel.
    *   `reportMetadata`: Information about the report itself (timestamps, technicians).
    *   `pendingReports`: Any reports mentioned as pending.

2.  **`patientInformation`**:
    *   Extract fields like `mrNo`, `name`, `labNo`, `dobAgeGender`, `doctor`, `referredClinic`, `mobileNo`, `encoDate`, `idPassport`, `nationality`.
    *   If "Vitals" are present (height, weight, BMI, hand grip), include them. Otherwise, mark as "Not available".

3.  **`overallReportSummary`**:
    *   Generate a comprehensive summary of the key findings (both normal and abnormal) for the patient in the report. This should be a concise paragraph written for a medical professional.

4.  **`recommendationsForDoctorsReview`**:
    *   This should be an object with categories like `cardiovascularHealthAndLipidManagement`, `inflammation`, `glucoseRegulationAndMetabolicStatus`, `electrolyteAndProteinBalance`, `hematologicalConsiderations`, `prostateHealth`, `generalWellnessAndPendingReports`.
    *   For each category, include `findings` (specific results that led to the recommendation) and `recommendation` (clinical advice/next steps).
    *   Add a `concludingNote` at the end stating: "These recommendations are generated based on the provided laboratory data. Comprehensive patient care requires correlation with the patient's full medical history, physical examination, and clinical presentation."

5.  **`detailedReports`**:
    *   This should contain an array `testList` listing all major test panel names.
    *   Then, include objects for different categories of tests (e.g., `biochemistry`, `endocrinologyImmuno`, `clinicalPathology`, `haematology`, `urinalysisByDipstickReagent`, etc.).
    *   Within each category, define panels (e.g., `lipidPanel`, `cReactiveProtein`, `hepaticFunctionPanel`).
    *   For each **panel**:
        *   `panelName`: The full name of the test panel.
        *   `overallSummary`: A brief clinical summary of the panel.
        *   `remarks` or `clinicalInterpretation` if provided in the report.
        *   `tests`: An array of individual test objects. For each test:
            *   `testName`
            *   `testResult` (include any 'H' or 'L' flags, e.g., "203 H")
            *   `units`
            *   `referenceRange`
            *   `status`: "High", "Low", or "Normal" based on the result and reference range.
            *   `method` (if available)
            *   `summary`: A concise, patient-friendly medical insight based on the result and status.
            *   If PSA, calculate `Free PSAPercentage` and include it with its interpretation.

6.  **`reportMetadata`**:
    *   Include `collectedOn`, `receivedOn`, `authenticatedOn`, `printedOn`, `reprintedOn` as formatted strings ("DD-MM-YYYY HH:MM:SS").
    *   Include a `technicians` array, with objects for each technician/pathologist, containing `name`, `role`, and `dhaP` (license/ID).

7.  **`pendingReports`**:
    *   Include keys for `devices` and `genetics` with appropriate text indicating they are pending.

**Handling Missing Information:**
*   If a specific data point is explicitly not found in the report, use `null` for numeric values or `"Not available in provided data"` for string fields.
*   For lists or objects that should be empty because no data was found, use `[]` or `{{}}` respectively.

**Example of how to determine 'status' for a test:**
*   If `testResult` is "203 H" and `referenceRange` is "Desirable:100-199", then `status` should be "High".
*   If `testResult` is "68 L" and `referenceRange` is "Normal : 70 - 99", then `status` should be "Low".
*   If `testResult` is "57" and `referenceRange` is "Low : <40, High: >60", then `status` should be "Normal".

**Output Format:**
Return the complete analysis as a single, well-formed JSON object.

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
