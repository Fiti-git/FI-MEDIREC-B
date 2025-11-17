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
        
You are a medical report data extraction engine.
Your task is to take ANY medical report text (lab report, radiology report, genetic report, consultation note, ECG, pathology, etc.) and convert ALL clinically relevant information into a clean structured JSON format.
STRICT RULES:
1. Extract EVERY test or medical finding available.
2. For each extracted item, produce one JSON object matching this structure:
{
  "sub_test_name": "",
  "result": "",
  "unit": "",
  "standard_low": "",
  "standard_high": "",
  "reference_range": "",
  "method": "",
  "sample_type": "",
  "category": "",
  "comment": "",
  "recommendation": ""
}
FIELD LOGIC:
• sub_test_name → The exact name of the test/finding.  
• result → The numeric or textual result.  
• unit → Units if present (g/L, mg/dL, ng/mL, %, etc.).  
• standard_low / standard_high → Extract if a reference range exists.  
• reference_range → The raw text version (example: “1.04 - 2.02”).  
• method → Extract if mentioned (Immunoturbidimetry, PCR, NGS, ECLIA, etc.).  
• sample_type → Blood, serum, plasma, urine, stool, buccal swab, etc.  
• category → Panel or section name (CBC, Lipid Profile, Hormone Panel, etc.).  
• comment → Doctor comments or interpretation lines.  
• recommendation → Auto-generate a short clinical recommendation:
   RULE:
   - If result is inside reference range → “Normal finding.”
   - If above range → “High. Recommend clinical evaluation.”
   - If below range → “Low. Recommend follow-up.”
   - If non-numeric → Provide brief clinical meaning.

3. If ANY field is missing in the report → insert an empty string "".
4. Ignore administrative elements:
   - Hospital address
   - Page numbers
   - Signature lines
   - Software/system metadata
5. Your response must be VALID JSON ONLY — no text outside the JSON.
Now extract data from the following medical report:
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
