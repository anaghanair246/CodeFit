from fastapi import APIRouter, HTTPException, status, Depends, Query
from starlette.requests import Request
from typing import Dict, List, Optional

from ....services.vertex_ai_service import (
    analyze_profile_text,
    generate_github_query_with_genai,
)
from ...v1.endpoints.auth import get_github_token
from ....services.github_service import (
    get_profile_text_data,
    get_user_profile,
)

router = APIRouter()


@router.get(
    "/analyze-profile",
    response_model=Dict[str, List[str]]
)
async def analyze_github_profile(
    request: Request,
    token: str = Depends(get_github_token),
):
    """
    Analyze the authenticated GitHub user's profile
    and extract relevant skills, technologies, and topics.
    """
    try:
        # Get profile information from GitHub
        profile_data = await get_profile_text_data(token)

        if not profile_data:
            profile_data = {}

        # Get additional user profile information
        user_profile = await get_user_profile(token)

        if not user_profile:
            user_profile = {}

        # Extract profile components
        languages = profile_data.get("languages", [])
        topics = profile_data.get("topics", [])
        text_blob = profile_data.get("text_blob", "")

        # Make sure values are valid lists/strings
        if not isinstance(languages, list):
            languages = []

        if not isinstance(topics, list):
            topics = []

        if not isinstance(text_blob, str):
            text_blob = ""

        # Build the text that will be analyzed
        combined_text = text_blob.strip()

        # Add GitHub bio
        bio = user_profile.get("bio")

        if bio:
            combined_text += f"\n\n{bio}"

        # Add programming languages
        if languages:
            combined_text += (
                "\n\nProgramming Languages: "
                + ", ".join(str(language) for language in languages)
            )

        # Add repository topics
        if topics:
            combined_text += (
                "\n\nTopics and Technologies: "
                + ", ".join(str(topic) for topic in topics)
            )

        # Nothing to analyze
        if not combined_text.strip():
            return {
                "keywords_entities": [],
                "languages": languages,
                "topics": topics,
            }

        # Analyze the actual GitHub profile data
        analysis_result = analyze_profile_text(combined_text)

        if not analysis_result:
            analysis_result = {
                "keywords_entities": [],
            }

        # Ensure expected response fields exist
        analysis_result["languages"] = languages
        analysis_result["topics"] = topics

        return analysis_result

    except HTTPException:
        raise

    except Exception as e:
        print(f"ERROR in analyze_github_profile: {str(e)}")

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to analyze GitHub profile.",
        )


@router.get(
    "/generate-query",
    response_model=Dict[str, str]
)
async def generate_github_query(
    request: Request,
    token: str = Depends(get_github_token),
    query_type: str = Query(
        "issues",
        description=(
            "Type of query to generate: "
            "'issues', 'repositories', or 'custom'"
        ),
    ),
    custom_prompt: Optional[str] = Query(
        None,
        description="Custom instructions for query generation",
    ),
):
    """
    Generate a GitHub search query based on the user's profile analysis.
    """
    try:
        # Analyze the user's GitHub profile
        profile_analysis = await analyze_github_profile(
            request=request,
            token=token,
        )

        # Extract analyzed information
        keywords = profile_analysis.get(
            "keywords_entities",
            []
        )

        languages = profile_analysis.get(
            "languages",
            []
        )

        topics = profile_analysis.get(
            "topics",
            []
        )

        # Generate the GitHub search query
        generated_query = generate_github_query_with_genai(
            keywords,
            languages,
            topics,
        )

        # Fallback query if AI generation fails
        if not generated_query:
            if languages:
                language_queries = " OR ".join(
                    f"language:{language}"
                    for language in languages[:2]
                )

                generated_query = (
                    f"state:open "
                    f"type:issue "
                    f"({language_queries}) "
                    f'label:"good first issue"'
                )

                if keywords:
                    generated_query += f" {keywords[0]}"

            else:
                generated_query = (
                    'state:open type:issue '
                    'label:"good first issue"'
                )

        # Return the generated query
        return {
            "query": generated_query,
            "query_type": query_type,
        }

    except HTTPException:
        raise

    except Exception as e:
        print(f"ERROR in generate_github_query: {str(e)}")

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate GitHub query.",
        )