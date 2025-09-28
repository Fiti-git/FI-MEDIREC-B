from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from .models import UploadedDocument, ExtractedText, ProcessedResult
from .serializers import (
    DocumentDetailSerializer,
    ExtractedTextDetailSerializer,
    ProcessedResultDetailSerializer
)

class DocumentHierarchyView(APIView):
    def get(self, request):
        # Get all documents, ordered by the most recently uploaded
        documents = UploadedDocument.objects.order_by('-uploaded_at').all()

        response_list = []

        for document in documents:
            # Use prefetch_related in a real-world scenario for optimization,
            # but for clarity, this direct query is fine.
            extracted_text = ExtractedText.objects.filter(document=document).first()
            processed_result = (
                ProcessedResult.objects.filter(extracted_text=extracted_text).first()
                if extracted_text else None
            )

            response_data = {
                "document": DocumentDetailSerializer(document).data,
                "extracted_text": ExtractedTextDetailSerializer(extracted_text).data if extracted_text else None,
                "processed_result": ProcessedResultDetailSerializer(processed_result).data if processed_result else None,
            }

            response_list.append(response_data)

        return Response(response_list, status=status.HTTP_200_OK)