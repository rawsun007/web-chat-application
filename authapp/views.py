from rest_framework import generics, permissions
from rest_framework.response import Response
from rest_framework.authtoken.models import Token
from django.contrib.auth import login
from .serializers import UserSerializer, RegisterSerializer, LoginSerializer

class RegisterAPI(generics.GenericAPIView):
    serializer_class = RegisterSerializer

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        token, created = Token.objects.get_or_create(user=user)
        return Response({
            "user": UserSerializer(user, context=self.get_serializer_context()).data,
            "token": token.key
        })

class LoginAPI(generics.GenericAPIView):
    serializer_class = LoginSerializer

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data
        login(request, user)
        token, created = Token.objects.get_or_create(user=user)
        return Response({
            "user": UserSerializer(user, context=self.get_serializer_context()).data,
            "token": token.key
        })

class UserAPI(generics.RetrieveAPIView):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = UserSerializer

    def get_object(self):
        return self.request.user
    

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
import requests
import json
from typing import Optional

import os
from dotenv import load_dotenv
import dj_database_url

# Load environment variables from .env file
load_dotenv()


# Access environment variables
BASE_API_URL = os.getenv("BASE_API_URL")
LANGFLOW_ID = os.getenv("LANGFLOW_ID")
FLOW_ID = os.getenv("FLOW_ID")
APPLICATION_TOKEN = os.getenv("APPLICATION_TOKEN")
ENDPOINT = os.getenv("ENDPOINT", "")  # You can set a specific endpoint name in the flow settings

TWEAKS = {
    "ChatInput-H8D4c": {},
    "ChatOutput-lbpA5": {},
    "File-PPYW6": {},
    "CustomComponent-c79R6": {},
    "HuggingFaceModel-wsmU0": {}
}

class LangflowAPI(APIView):
    """
    A view to handle the LangFlow chat functionality.
    Accepts a POST request with the message and customizations (optional).
    """

    def post(self, request, *args, **kwargs):
        message = request.data.get("message", "").strip()
        tweaks = request.data.get("tweaks", TWEAKS)
        application_token = request.data.get("application_token", APPLICATION_TOKEN)

        # Debug: Print message and tweaks received in the request
        print("Received message:", message)
        print("Received tweaks:", tweaks)

        if not message:
            return Response({"error": "Message cannot be empty."}, status=status.HTTP_400_BAD_REQUEST)

        # Run LangFlow API with the given message and optional tweaks
        response = self.run_langflow(message, tweaks, application_token)

        # Debug: Print response from LangFlow API
        print("Response from LangFlow API:", response)

        return Response(response, status=status.HTTP_200_OK)

    def run_langflow(self, message: str, tweaks: Optional[dict] = None, application_token: Optional[str] = None) -> dict:
        """
        Run the LangFlow API with the provided message and optional tweaks.

        :param message: The message to send to the LangFlow API.
        :param tweaks: Optional dictionary of tweaks to customize the flow.
        :param application_token: The application token for authentication.
        :return: The response JSON from LangFlow API.
        """
        api_url = f"{BASE_API_URL}/lf/{LANGFLOW_ID}/api/v1/run/{ENDPOINT or FLOW_ID}"

        payload = {
            "input_value": message,
            "output_type": "chat",
            "input_type": "chat",
            "tweaks": tweaks if tweaks else TWEAKS
        }

        headers = {"Authorization": f"Bearer {application_token}", "Content-Type": "application/json"}

        # Debug: Print the API request URL and payload
        print("Request URL:", api_url)
        print("Request Payload:", json.dumps(payload, indent=2))

        try:
            response = requests.post(api_url, json=payload, headers=headers)

            # Debug: Print raw response status and content before processing
            print("Raw Response Status:", response.status_code)
            print("Raw Response Content:", response.text)

            response.raise_for_status()  # Raises HTTPError for bad responses
            return response.json()

        except requests.exceptions.HTTPError as errh:
            print("HTTP Error:", errh)  # Debug: Print error message
            return {"error": f"HTTP Error: {errh}"}
        except requests.exceptions.RequestException as err:
            print("Request Error:", err)  # Debug: Print error message
            return {"error": f"Request Error: {err}"}
