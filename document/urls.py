from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    UploadedDocumentViewSet,
    ExtractedTextViewSet,
    ProcessedResultViewSet,
    UploadedDocumentIDListView,
    delete_document  # Import the custom delete view
)

# DRF router for viewsets
router = DefaultRouter()
router.register(r'uploads', UploadedDocumentViewSet)
router.register(r'extracted', ExtractedTextViewSet)
router.register(r'results', ProcessedResultViewSet)

urlpatterns = [
    # ✅ Put custom route BEFORE the router
    path('uploads/ids/', UploadedDocumentIDListView.as_view(), name='uploaded-document-ids'),
    
    # Custom delete document route
    path('uploads/delete_document/<int:document_id>/', delete_document, name='delete-document'),

    # Then include the router URLs
    path('', include(router.urls)),
]
