from fastapi import APIRouter, UploadFile, File, HTTPException
from models.scene import SceneGraph, SceneObject
from services.scene_analyzer import scene_analyzer

router = APIRouter()

@router.get("/api/scenes/{scene_id}", response_model=SceneGraph)
async def get_scene(scene_id: str):
    # For MVP, return the demo scene regardless of ID
    # In a real app, this would fetch from a DB using scene_id
    try:
        return scene_analyzer.get_demo_scene()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/api/analyze", response_model=SceneGraph)
async def analyze_scene(file: UploadFile = File(...)):
    try:
        contents = await file.read()
        return await scene_analyzer.analyze(contents)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/api/scenes/{scene_id}/objects", response_model=list[SceneObject])
async def get_objects(scene_id: str):
    try:
        scene = scene_analyzer.get_demo_scene()
        return scene.objects
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
