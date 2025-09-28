import json
from rest_framework import serializers
from .models import UploadedDocument, ExtractedText, ProcessedResult

class DocumentDetailSerializer(serializers.ModelSerializer):
    class Meta:
        model = UploadedDocument
        fields = '__all__'

class ExtractedTextDetailSerializer(serializers.ModelSerializer):
    class Meta:
        model = ExtractedText
        fields = '__all__'

# --- START OF MODIFIED SERIALIZER ---
class ProcessedResultDetailSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProcessedResult
        fields = '__all__'

    def to_representation(self, instance):
        """
        Override the default representation to parse the raw_response string
        into a proper JSON object before sending it to the frontend.
        """
        # Get the default serialized data (all fields)
        representation = super().to_representation(instance)
        
        # The 'data' field is a dict. We need to check if 'raw_response' exists within it.
        data_field = representation.get('data')
        if data_field and isinstance(data_field, dict):
            raw_response_str = data_field.get('raw_response')
            
            # Check if raw_response_str is indeed a string that needs parsing
            if raw_response_str and isinstance(raw_response_str, str):
                try:
                    # Attempt to clean markdown fences before parsing
                    if raw_response_str.startswith('```json'):
                        # Find the first newline and start after it
                        clean_str = raw_response_str[raw_response_str.find('\n') + 1:-3].strip()
                    elif raw_response_str.startswith('```'):
                         clean_str = raw_response_str[3:-3].strip()
                    else:
                        clean_str = raw_response_str
                        
                    # Parse the cleaned string into a Python dict/list
                    parsed_json = json.loads(clean_str)
                    
                    # Replace the string in the 'data' field with the parsed object
                    data_field['raw_response'] = parsed_json
                    
                except json.JSONDecodeError:
                    # If parsing fails (e.g., truncated data in DB),
                    # leave the original (potentially broken) string.
                    # This makes the API robust, and the frontend can handle it.
                    pass # Keep the original raw_response_str

        return representation

# --- END OF MODIFIED SERIALIZER ---


class FullDocumentInfoSerializer(serializers.Serializer):
    """
    This serializer is not currently used in the view but is kept for potential future use.
    """
    document = DocumentDetailSerializer()
    extracted_text = ExtractedTextDetailSerializer()
    processed_result = ProcessedResultDetailSerializer()


class DocumentIDSerializer(serializers.ModelSerializer):
    class Meta:
        model = UploadedDocument
        fields = ['id']