from django.db import connection
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView


class HealthView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(summary="健康检查", tags=["system"])
    def get(self, request):
        db_ok = True
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                cursor.fetchone()
        except Exception:
            db_ok = False
        return Response(
            {
                "status": "ok" if db_ok else "degraded",
                "database": "ok" if db_ok else "error",
                "time": timezone.now().isoformat(),
                "version": "1.0.0",
            }
        )
