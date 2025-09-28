from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from .models import UploadedDocument, ExtractedText, ProcessedResult
from .serializers import DocumentDetailSerializer as UploadedDocumentSerializer
from .serializers import ExtractedTextDetailSerializer as ExtractedTextSerializer
from .serializers import ProcessedResultDetailSerializer as ProcessedResultSerializer
from .serializers import DocumentIDSerializer
from rest_framework import generics
from .task import extract_and_analyze  # ✅ Import background task
from django.http import FileResponse
from .pdf_utils import generate_report_pdf
from django.shortcuts import get_object_or_404
from django.http import HttpResponse
from django.core.exceptions import ObjectDoesNotExist


class UploadedDocumentViewSet(viewsets.ModelViewSet):
    queryset = UploadedDocument.objects.all()
    serializer_class = UploadedDocumentSerializer

    def perform_create(self, serializer):
        uploaded_document = serializer.save()

        # ✅ Queue background task to extract text and analyze
        extract_and_analyze(uploaded_document.id)

        print(f"[INFO] Uploaded document ID {uploaded_document.id} queued for processing.")


class ExtractedTextViewSet(viewsets.ModelViewSet):
    queryset = ExtractedText.objects.all()
    serializer_class = ExtractedTextSerializer

    @action(detail=True, methods=['post'])
    def analyze(self, request, pk=None):
        return Response({
            "message": "This endpoint is no longer used. Analysis is now automatic via background tasks."
        }, status=status.HTTP_410_GONE)  # Optional: deprecate manual analyze endpoint


class ProcessedResultViewSet(viewsets.ModelViewSet):
    queryset = ProcessedResult.objects.all()
    serializer_class = ProcessedResultSerializer

    @action(detail=True, methods=["get"])
    def download_pdf(self, request, pk=None):
        processed_result = self.get_object()
        pdf_path = generate_report_pdf(processed_result)

        # Save path to DB (optional)
        processed_result.pdf_file.name = f"reports/report_{processed_result.id}.pdf"
        processed_result.save(update_fields=["pdf_file"])

        return FileResponse(open(pdf_path, "rb"), as_attachment=True, filename=f"report_{processed_result.id}.pdf")


class UploadedDocumentIDListView(generics.ListAPIView):
    queryset = UploadedDocument.objects.all()
    serializer_class = DocumentIDSerializer


def delete_document(request, document_id):
    try:
        # Get the document to be deleted
        uploaded_document = get_object_or_404(UploadedDocument, id=document_id)

        # Check if the document has associated extracted text or processed results
        extracted_texts = uploaded_document.extracted_text.all()
        processed_results = ProcessedResult.objects.filter(extracted_text__document=uploaded_document)

        # Delete associated text files
        for extracted_text in extracted_texts:
            extracted_text.delete()  # This will delete the associated text file but keep the data

        # Delete associated processed results but keep JSON data
        for result in processed_results:
            # Only delete the PDF file for the processed result, keep JSON data intact
            if result.pdf_file:
                result.pdf_file.delete()  # Delete the generated PDF file
            # Note: The `data` field (JSON) will remain intact in the database, no need to delete

        # Finally delete the document itself (PDF file) but keep the data
        if uploaded_document.file:
            uploaded_document.file.delete()  # Delete the PDF file

        # Optionally, you can leave the document entry in the database with a specific status (e.g., 'deleted')
        # uploaded_document.delete()  # If you want to completely delete the document, uncomment this

        # Return success message
        return HttpResponse("Document and associated PDF files deleted successfully. JSON data is preserved.")
    
    except ObjectDoesNotExist:
        return HttpResponse("Document not found.", status=404)
    
    except Exception as e:
        return HttpResponse(f"An error occurred: {str(e)}", status=500)
