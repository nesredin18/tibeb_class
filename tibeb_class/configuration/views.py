from rest_framework.response import Response
from rest_framework.decorators import api_view
from .models import Configuration
from .serializers import ConfigurationSerializer

@api_view(['GET'])
def get_configuration(request):
    """
    Return the latest (or single) configuration record.
    """
    config = Configuration.objects.order_by('-id').first()
    serializer = ConfigurationSerializer(config)
    return Response(serializer.data)
