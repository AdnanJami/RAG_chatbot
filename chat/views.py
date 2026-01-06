import os
from time import timezone
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from groq import Groq
from pinecone import Pinecone
from .models import ChatMessage
from .serializers import ChatMessageSerializer, ChatRequestSerializer
from datetime import  timedelta
from apscheduler.schedulers.background import BackgroundScheduler
# Initialize clients
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "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")
PINECONE_API_KEY = os.getenv("PINECONE_API_KEY", "pcsk_5Cfeu8_3BPfxgHxH7Ev8ZJhBwesLpSdHTKecDZ7eRZadva49co6wa8xakt2eEjLpJvs95B")

def get_groq_client():
    return Groq(api_key=GROQ_API_KEY)

def get_pinecone_index():
    pc = Pinecone(api_key=PINECONE_API_KEY)
    return pc.Index("django")


MODEL = "openai/gpt-oss-120b"
SYSTEM_PROMPT = "You are a helpful, concise, and friendly assistant."
MAX_TOKENS = 1024
TEMPERATURE = 0.6


def retrieve_relevant_chunks(query: str, top_k: int = 5) -> str:
    """Return concatenated text of top-k relevant chunks from Pinecone."""
    
    index = get_pinecone_index() 

    results = index.search(
        namespace="ns1",
        query={
            "top_k": top_k,
            "inputs": {"text": query}
        }
    )

    context = ""
    for hit in results["result"]["hits"]:
        chunk_text = hit["fields"]["chunk_text"]
        context += chunk_text + "\n---\n"
    return context



def truncate_history(messages: list, max_total_tokens: int = 7500) -> list:
    approx_tokens = sum(len(m["content"]) // 4 for m in messages)
    while approx_tokens > max_total_tokens and len(messages) > 2:
        messages.pop(1)
        messages.pop(1)
        approx_tokens = sum(len(m["content"]) // 4 for m in messages)
    return messages


class ChatHistoryView(APIView):
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        messages = ChatMessage.objects.filter(user=request.user)
        serializer = ChatMessageSerializer(messages, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)


class ChatView(APIView):
    permission_classes = [IsAuthenticated]
    
    def post(self, request):
        serializer = ChatRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        user_message = serializer.validated_data['message']
        
        ChatMessage.objects.create(
            user=request.user,
            role='user',
            content=user_message
        )
        
        try:
            context = retrieve_relevant_chunks(user_message, top_k=5)
            
            history = [{"role": "system", "content": SYSTEM_PROMPT}]
            
            recent_messages = ChatMessage.objects.filter(user=request.user).order_by('-timestamp')[:20]
            for msg in reversed(recent_messages):
                history.append({"role": msg.role, "content": msg.content})
            
            prompt = f"Use the following context to answer the question. If unsure, answer based on the context.\n\nContext:\n{context}\nQuestion: {user_message}"
            history.append({"role": "user", "content": prompt})
            
            history = truncate_history(history, max_total_tokens=7500)
            
            groq_client = get_groq_client()
            response = groq_client.chat.completions.create(
                model=MODEL,
                messages=history,
                temperature=TEMPERATURE,
                max_tokens=MAX_TOKENS
            )
            
            assistant_message = response.choices[0].message.content
            
            ChatMessage.objects.create(
                user=request.user,
                role='assistant',
                content=assistant_message
            )
            
            return Response({
                "message": assistant_message
            }, status=status.HTTP_200_OK)
            
        except Exception as e:
            return Response({
                "error": str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)




def start():
    scheduler = BackgroundScheduler()
    scheduler.add_job(delete_chat, 'interval', minutes=60)
    scheduler.start()


def delete_chat():
    print("Deleting old chat messages...")
    cutoff_date = timezone.now() - timedelta(days=30)

    old_messages = ChatMessage.objects.filter(
            timestamp__lt=cutoff_date
        )

    old_messages.delete()