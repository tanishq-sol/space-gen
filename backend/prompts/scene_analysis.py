SCENE_ANALYSIS_PROMPT = """
You are an expert interior design analyst. Analyze this room image and extract a structured scene description.

For each visible object, provide:
- entity_id (e.g., sofa_01, coffee_table_01, wall_north)
- type: one of [architecture, furniture, lighting, decor]
- category: specific type (wall, sofa, coffee_table, lamp, plant, rug, etc.)
- material: {type, color, finish}
- style description
- estimated dimensions in meters
- confidence (0-1)
- editable: true for furniture/decor, false for architecture

Also identify:
- Room type
- Overall design style
- Lighting conditions
- Key spatial relationships

Return ONLY valid JSON matching the provided schema. Be precise. Do not hallucinate objects not visible in the image.
"""
