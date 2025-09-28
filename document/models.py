from django.db import models

class UploadedDocument(models.Model):
    title = models.CharField(max_length=255)
    file = models.FileField(upload_to='documents/')
    uploaded_at = models.DateTimeField(auto_now_add=True)

    # New status field to track extraction
    extraction_status = models.CharField(max_length=20, default='pending')
    extraction_started_at = models.DateTimeField(null=True, blank=True)
    extraction_finished_at = models.DateTimeField(null=True, blank=True)
    extraction_error = models.TextField(null=True, blank=True)

    def __str__(self):
        return self.title


class ExtractedText(models.Model):
    document = models.ForeignKey(UploadedDocument, on_delete=models.CASCADE, related_name='extracted_text')
    text_file = models.FileField(upload_to='texts/')
    extracted_at = models.DateTimeField(auto_now_add=True)

    # New status field to track processing with Gemini
    processing_status = models.CharField(max_length=20, default='pending')
    processing_started_at = models.DateTimeField(null=True, blank=True)
    processing_finished_at = models.DateTimeField(null=True, blank=True)
    processing_error = models.TextField(null=True, blank=True)

    def __str__(self):
        return f"Text from {self.document.title}"


class ProcessedResult(models.Model):
    extracted_text = models.ForeignKey(ExtractedText, on_delete=models.CASCADE, related_name='processed_results')
    data = models.JSONField()
    processed_at = models.DateTimeField(auto_now_add=True)

    # New field to store the generated report PDF
    pdf_file = models.FileField(upload_to="reports/", null=True, blank=True)

    def __str__(self):
        return f"Result for {self.extracted_text.document.title}"
