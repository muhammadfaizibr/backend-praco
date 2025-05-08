from rest_framework import renderers
import json
from decimal import Decimal

class DecimalEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, Decimal):
            return str(obj)  # Convert Decimal to string for JSON serialization
        return super().default(obj)

class CustomRenderer(renderers.JSONRenderer):
    charset = "utf-8"
    def render(self, data, accepted_media_type=None, renderer_context=None):
        response = ""
        if "ErrorDetail" in str(data):
            response = json.dumps({"errors": data}, cls=DecimalEncoder)
        else:
            response = json.dumps(data, cls=DecimalEncoder)
            
        return response