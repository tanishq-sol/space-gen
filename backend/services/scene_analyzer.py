import json
import os
from models.scene import SceneGraph
from services.gemini_agent import GeminiAgent
from config import settings

class SceneAnalyzer:
    def __init__(self):
        self.agent = GeminiAgent(
            api_key=settings.gemini_api_key,
            default_model=settings.gemini_reasoning_model
        )
        
    async def analyze(self, image_bytes: bytes) -> SceneGraph:
        try:
            return await self.agent.analyze_scene(image_bytes)
        except Exception as e:
            print(f"Analysis failed, falling back to demo data: {e}")
            return self.get_demo_scene()
            
    def get_demo_scene(self) -> SceneGraph:
        demo_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "demo_scene.json")
        try:
            with open(demo_path, "r") as f:
                data = json.load(f)
                return SceneGraph.model_validate(data)
        except Exception as e:
            print(f"Failed to load demo scene: {e}")
            # Return a minimal empty scene if everything fails
            return SceneGraph(
                scene_id="fallback",
                room_type="unknown",
                style="unknown",
                objects=[]
            )

scene_analyzer = SceneAnalyzer()
