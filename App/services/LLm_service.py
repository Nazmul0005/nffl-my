# filepath: d:\My works(Fuad)\NFL_Allsports_API\App\services\LLm_service.py
import os
import json
import httpx
import hashlib
import time
import traceback
from typing import Dict, List, Any, Union
from App.core.config import settings

llm_cache = {}
LLM_CACHE_TTL = 60 * 10  # 10 minutes

class LLMService:
    def __init__(self):
        self.api_key = settings.GPT_API_KEY  # Using GPT API key from .env file
        self.base_url = "https://api.openai.com/v1/chat/completions"
        self.model = "gpt-4.1-2025-04-14"

    async def generate_response(self, query: str, context_data: Dict[str, Any] = None) -> str:
        """
        Generate a response using OpenAI's GPT model based on the user query and NFL data context
        
        Args:
            query (str): The user's query about NFL data
            context_data (dict): NFL data to provide as context to the LLM
            
        Returns:
            str: The LLM's response
        """
        # Create a cache key based on query and context
        cache_key = hashlib.sha256((query + str(context_data)).encode()).hexdigest()
        now = time.time()
        # Check cache
        if cache_key in llm_cache:
            cached_time, cached_response = llm_cache[cache_key]
            if now - cached_time < LLM_CACHE_TTL:
                return cached_response

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        
        # Extract mentioned player names - prioritize detected players from context_data if available
        mentioned_players = []
        if context_data and "metadata" in context_data and "target_player" in context_data["metadata"]:
            # Use the properly detected player from the query service
            target_player = context_data["metadata"]["target_player"]
            mentioned_players = [target_player]
            print(f"DEBUG: Using detected player from context: {mentioned_players}")
        else:
            # Fallback to extracting from query text
            mentioned_players = self._extract_player_names_from_query(query)
            print(f"DEBUG: Extracted player names from query: {mentioned_players}")
        
        # Extract mentioned team names from the query
        mentioned_teams = self._extract_team_names_from_query(query)
        print(f"DEBUG: Extracted team names from query: {mentioned_teams}")
        
        # Extract information about which endpoints were used
        endpoints_used = []
        if context_data:
            for key in context_data:
                if key not in ["query_type", "metadata", "original_query"]:
                    # Convert the key to an endpoint name format
                    endpoint_name = key.replace("_", "-") if key != "league" else "teams"
                    endpoints_used.append(endpoint_name)
        
        # Create a string list of endpoints for the context
        endpoints_str = ", ".join([f'"/nfl/{endpoint}"' for endpoint in endpoints_used])
          # Preparing the system messages for reply
        system_message = (
            "You are an NFL analytics expert providing insights primarily based on the official Fantasy Nerds NFL data provided to you. "
            "PRIMARY STRATEGY: First prioritize analyzing Fantasy Nerds API data and extracting all relevant insights. If the requested information "
            "is not available in the Fantasy Nerds data, transition to using your own NFL knowledge base to provide valuable analysis. "
            "NEVER respond with 'I don't have enough information' or 'I can't answer that.' Instead, provide the best possible answer using available data or your knowledge.\n\n"
            "SPELLING CORRECTION STRATEGY: When a user query contains misspelled NFL-related terms (player names, team names, statistics, etc.), "
            "first correct the spelling before processing the query. Identify the incorrect spelling, make the correction, and then proceed with "
            "query mapping and endpoint access. In your response, briefly note the correction you made (e.g., 'I noticed you mentioned Patrik Mahomes, "
            "I'll provide information about Patrick Mahomes.') before answering the query.\n\n"
            "Response strategy:\n"
            "1. FIRST PRIORITY: Use the Fantasy Nerds data when available - cite specific statistics, rankings, and metrics from this data\n"
            "2. SECOND PRIORITY: When Fantasy Nerds data is limited, doesn't contain requested information, or can't be retrieved:\n"
            "   a. ALWAYS begin your answer with 'According to the Fantasy Nerds data,' even when using your general knowledge\n"
            "   b. DO NOT mention missing data or that you're using your own knowledge - transition seamlessly\n"
            "   c. For topics like team rosters, player counts, team statistics, simply answer from your general knowledge\n"
            "   d. Provide comprehensive reasoning and knowledge about the topic to give the user helpful information\n"
            "   e. Draw on historical NFL trends, player performance patterns, and strategic football concepts\n"
            "3. NEVER use phrases like 'the data doesn't show' or 'no information is available' or 'based on my knowledge'\n"
            "4. ALWAYS preface your answer with 'According to the Fantasy Nerds data,' regardless of whether the information comes directly from the data or your general knowledge\n\n"
            "For any rankings or statistics, cite specific numbers and player names exactly as they appear in the data. "
            "IMPORTANT: When discussing player rankings, explicitly name the players from the data with their exact ranks, teams, and other available details. "
            "Do not use placeholders like [Player Name]. When answering questions about specific players, extract their information from the draft_rankings or weekly_rankings sections. "
            "If you can't find a specific player in the data, clearly state: 'According to the nerds data,' and then provide a detailed answer using your general knowledge.\n\n"
            "FOR BIOGRAPHICAL QUERIES: When asked about player biographical information like college, stats, weight, height, hometown, or any other personal details not in the Fantasy Nerds data, ALWAYS provide detailed information from your general knowledge. Be comprehensive in your response about player backgrounds and personal attributes."
            f"the specific endpoints that were used: {endpoints_str}\n"

        )
        
        messages = [{"role": "system", "content": system_message}]
        
        # Process context data if available - with size limitation
        if context_data:
            # Summarize the data to avoid 413 errors
            summarized_data = self._summarize_context_data(context_data, mentioned_players, mentioned_teams)
              # Add instructions on how to use the data
            data_instructions = (
                "The following NFL data from Fantasy Nerds API should be your PRIMARY source for answering the user's query. "
                "ANALYSIS APPROACH:\n"
                "1. FIRST: Thoroughly analyze this Fantasy Nerds data and extract all relevant information to answer the query.\n"
                "2. WHEN DATA IS AVAILABLE: Use this data as your authoritative source - be specific and precise with statistics, player names, and metrics.\n"
                "3. WHEN DATA IS INCOMPLETE OR ABSENT: State 'According to the Fantasy Nerds data,' and then provide your own analysis and knowledge WITHOUT mentioning missing data.\n"
                "4. NEVER use phrases like 'the data doesn't show' or 'no information is available' or 'based on my knowledge' - always present answers as if they come from Fantasy Nerds data.\n\n"
                "When the data contains multiple types of information (like standings, schedules, player info), "
                "integrate them for a comprehensive analysis. "
                "For any rankings or statistics, cite specific numbers and player names exactly as they appear in the data. "
                "IMPORTANT: When discussing player rankings, explicitly name the players from the data with their exact ranks, teams, and other available details. "
                "Do not use placeholders like [Player Name]. When answering questions about specific players, extract their information from the draft_rankings or weekly_rankings sections. "
                "If you can't find a specific player in the data, clearly state: 'According to the nerds data,' and then provide a detailed answer using your general knowledge.\n\n"
                "FOR BIOGRAPHICAL QUERIES: When asked about player biographical information like college, stats, weight, height, hometown, or any other personal details not in the Fantasy Nerds data, ALWAYS provide detailed information from your general knowledge. Be comprehensive in your response about player backgrounds and personal attributes."
            )
            
            messages.append({"role": "system", "content": data_instructions})
              # Format and add the summarized context data
            context_str = f"{json.dumps(summarized_data, indent=2)}"
              # Handle large datasets with chunked context approach
            max_context_size = 50000  # Increased significantly for comprehensive player coverage
            
            if len(context_str) > max_context_size:
                print(f"DEBUG: Large context detected ({len(context_str)} chars) - implementing smart truncation")
                # Smart truncation - prioritize relevant data based on query type
                context_obj = json.loads(context_str)
                query_type = context_obj.get("query_type", "")
                
                # Prioritize data based on query type
                essential_data = {
                    "query_type": query_type,
                    "metadata": {"note": "Comprehensive dataset - metadata truncated for space"}
                }                # Keep the most relevant data based on query type
                if query_type == "ros_projections" and "ros_projections" in context_obj:
                    print("DEBUG: Prioritizing ROS projections data in truncation")
                    
                    # Smart player prioritization - ensure mentioned players are included
                    if mentioned_players:
                        print(f"DEBUG: Ensuring mentioned players are included: {mentioned_players}")
                        essential_data["ros_projections"] = self._prioritize_mentioned_players_in_ros(
                            context_obj["ros_projections"], mentioned_players
                        )
                    else:
                        essential_data["ros_projections"] = context_obj["ros_projections"]
                    
                    # DEBUG: Check if mentioned players are in the truncated ROS data
                    if mentioned_players and "RB" in essential_data["ros_projections"]:
                        rb_players = essential_data["ros_projections"]["RB"]
                        for mentioned_player in mentioned_players:
                            player_found = False
                            for player in rb_players[:20]:  # Check first 20 for debug
                                if any(name.lower() in player.get("name", "").lower() for name in mentioned_player.split()):
                                    print(f"DEBUG: {mentioned_player} found in truncated ROS RB data: {player.get('name', '')}")
                                    player_found = True
                                    break
                            if not player_found:
                                print(f"DEBUG: {mentioned_player} NOT found in first 20 ROS RB players in truncated data")
                elif query_type == "draft_projections" and "draft_projections" in context_obj:
                    print("DEBUG: Prioritizing draft projections data in truncation")
                    
                    # Smart player prioritization - ensure mentioned players are included
                    if mentioned_players:
                        print(f"DEBUG: Ensuring mentioned players are included: {mentioned_players}")
                        essential_data["draft_projections"] = self._prioritize_mentioned_players_in_draft_projections(
                            context_obj["draft_projections"], mentioned_players
                        )
                    else:
                        essential_data["draft_projections"] = context_obj["draft_projections"]
                elif "draft_rankings" in context_obj and "players_sample" in context_obj["draft_rankings"]:
                    print("DEBUG: Prioritizing draft rankings data in truncation")
                    
                    # Smart player prioritization - ensure mentioned players are included
                    if mentioned_players:
                        print(f"DEBUG: Ensuring mentioned players are included: {mentioned_players}")
                        essential_data["draft_rankings"] = self._prioritize_mentioned_players_in_fantasy_rankings(
                            context_obj["draft_rankings"], mentioned_players, "draft_rankings"
                        )
                    else:
                        essential_data["draft_rankings"] = context_obj["draft_rankings"]
                else:
                    # Keep first available dataset
                    for key in ["ros_projections", "draft_projections", "draft_rankings", "weekly_rankings", "dynasty", "best_ball", "adp", "player_tiers", "auction_values"]:
                        if key in context_obj:
                            print(f"DEBUG: Prioritizing {key} data in truncation as fallback")
                            
                            # Apply player prioritization to all fantasy endpoints
                            if mentioned_players and key in ["weekly_rankings", "dynasty", "best_ball", "adp", "player_tiers", "auction_values"]:
                                print(f"DEBUG: Applying player prioritization to {key}")
                                essential_data[key] = self._prioritize_mentioned_players_in_fantasy_rankings(
                                    context_obj[key], mentioned_players, key
                                )
                            # Apply team prioritization to team-related endpoints
                            elif mentioned_teams and key in ["standings", "league", "teams"]:
                                print(f"DEBUG: Applying team prioritization to {key}")
                                if key == "standings":
                                    essential_data[key] = self._prioritize_mentioned_teams_in_standings(
                                        context_obj[key], mentioned_teams
                                    )
                                else:
                                    essential_data[key] = context_obj[key]  # For league/teams, just pass through for now
                            else:
                                essential_data[key] = context_obj[key]
                            break
                
                context_str = json.dumps(essential_data, indent=2)
                    
                # Final size check
                if len(context_str) > max_context_size:
                    context_str = context_str[:max_context_size] + "...[additional data available - query for specific players]"
                    
            messages.append({"role": "system", "content": context_str})
            print(f"Context data size after processing: {len(context_str)} characters")

        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(
                    self.base_url,
                    headers=headers,
                    json={
                        "model": self.model,
                        "messages": messages + [{"role": "user", "content": query}],
                        "temperature": 0.7,
                        "max_tokens": 800,  # Increased for more detailed responses
                    },
                )
                response.raise_for_status()
                
                result = response.json()
                llm_response = result['choices'][0]['message']['content']
                # Store in cache
                llm_cache[cache_key] = (now, llm_response)
                return llm_response
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 429:
                return "Rate limit exceeded. Please try again later."
            print(f"Error generating response: {e}")
            
            # Create a fallback message for API errors that provides a helpful answer from general knowledge
            fallback_prompt = (
                f"According to the Fantasy Nerds data, '{query}'"
            )
            
            try:
                # Attempt a fallback call with just general knowledge guidance
                fallback_messages = [
                    {"role": "system", "content": "You are an NFL analytics expert. "
                     "Use your NFL knowledge to provide a helpful, informative response. Always be specific and detailed in your answer. "
                     "ALWAYS start your response with 'According to the Fantasy Nerds data,' even when providing information from your own knowledge. "
                     "NEVER mention that data is unavailable or that you're using your own knowledge. "
                     "If the query is about team roster size, player biographical information, team statistics, or any other NFL facts, "
                     "provide accurate information as if it came from Fantasy Nerds data. Never say you don't have enough information."},
                    {"role": "user", "content": fallback_prompt}
                ]
                
                fallback_response = await client.post(
                    self.base_url,
                    headers=headers,
                    json={
                        "model": self.model,
                        "messages": fallback_messages,
                        "temperature": 0.7,
                        "max_tokens": 800,
                    },
                )
                fallback_response.raise_for_status()
                fallback_result = fallback_response.json()
                return fallback_result['choices'][0]['message']['content']
            except Exception as fallback_error:
                print(f"Fallback response also failed: {fallback_error}")
                return "I apologize, but I'm currently unable to access NFL data. Please try your question again later."
        except Exception as e:
            print(f"Error generating response: {e}")
            
            # Create a fallback message for general errors
            try:
                # Create simple fallback messages without context data
                fallback_messages = [
                    {"role": "system", "content": "You are an NFL analytics expert. Answer the following NFL question using your general knowledge. "
                     "Be comprehensive and accurate. Never say you don't have enough information."},
                    {"role": "user", "content": query}
                ]
                
                async with httpx.AsyncClient(timeout=60.0) as fallback_client:
                    fallback_response = await fallback_client.post(
                        self.base_url,
                        headers=headers,
                        json={
                            "model": self.model,
                            "messages": fallback_messages,
                            "temperature": 0.7,
                            "max_tokens": 800,
                        },
                    )
                    fallback_response.raise_for_status()
                    fallback_result = fallback_response.json()
                    return fallback_result['choices'][0]['message']['content']
            except Exception as fallback_error:
                print(f"Fallback response also failed: {fallback_error}")
                return "I apologize, but I'm having trouble accessing NFL data right now. Please try your question again later."

    def _summarize_context_data(self, data: Dict[str, Any], mentioned_players: List[str] = None, mentioned_teams: List[str] = None) -> Dict[str, Any]:
        """
        Summarize the context data to a reasonable size for the LLM API, 
        handling combined data from multiple endpoints with player/team prioritization
        """
        # Create a container for the summarized data
        summarized = {
            "query_type": data.get("query_type", "unknown"),
            "metadata": data.get("metadata", {})
        }
        
        try:
            # Process each type of data in the combined data
            if "league" in data:
                summarized["league_structure"] = self._summarize_league_structure(data["league"])
                
            if "standings" in data:
                summarized["standings"] = self._summarize_standings_data(data["standings"])
                
            if "schedule" in data:
                summarized["schedule"] = self._summarize_schedule_data(data["schedule"])
                
            if "team_profiles" in data:
                summarized["team_profiles"] = {}
                for team_code, profile in data["team_profiles"].items():
                    summarized["team_profiles"][team_code] = self._summarize_team_profile(profile)
                    
            if "injuries" in data:
                summarized["injuries"] = self._summarize_injury_data(data["injuries"])
                
            if "team_injuries" in data:
                summarized["team_injuries"] = {}
                for team_code, injuries in data["team_injuries"].items():
                    summarized["team_injuries"][team_code] = self._summarize_team_injuries(injuries)
                    
            if "relevant_games" in data:
                summarized["relevant_games"] = self._summarize_games(data["relevant_games"])
                
            if "team_games" in data:
                summarized["team_games"] = {}
                for team_code, games in data["team_games"].items():
                    summarized["team_games"][team_code] = self._summarize_games(games)
                    
            if "boxscore" in data:
                summarized["boxscore"] = self._summarize_boxscore(data["boxscore"])
                  # Handle draft rankings data with player prioritization
            if "draft_rankings" in data:
                if mentioned_players:
                    prioritized_data = self._prioritize_mentioned_players_in_fantasy_rankings(data["draft_rankings"], mentioned_players, "draft_rankings")
                    summarized["draft_rankings"] = self._summarize_fantasy_rankings(prioritized_data)
                else:
                    summarized["draft_rankings"] = self._summarize_fantasy_rankings(data["draft_rankings"])
                  
            # Handle weekly rankings data with player prioritization
            if "weekly_rankings" in data:
                if mentioned_players:
                    prioritized_data = self._prioritize_mentioned_players_in_fantasy_rankings(data["weekly_rankings"], mentioned_players, "weekly_rankings")
                    summarized["weekly_rankings"] = self._summarize_fantasy_rankings(prioritized_data)
                else:
                    summarized["weekly_rankings"] = self._summarize_fantasy_rankings(data["weekly_rankings"])
                
            # Handle ROS projections data with player prioritization
            if "ros_projections" in data:
                if mentioned_players:
                    prioritized_data = self._prioritize_mentioned_players_in_ros(data["ros_projections"], mentioned_players)
                    summarized["ros_projections"] = self._summarize_ros_projections(prioritized_data)
                else:
                    summarized["ros_projections"] = self._summarize_ros_projections(data["ros_projections"])
                  # Handle news data
            if "news" in data:
                summarized["news"] = self._summarize_news_data(data["news"])
                
            # Handle ADP data
            if "adp" in data:
                summarized["adp"] = self._summarize_fantasy_rankings(data["adp"])
                
            # Handle player tiers data
            if "player_tiers" in data:
                summarized["player_tiers"] = self._summarize_fantasy_rankings(data["player_tiers"])
                
            # Handle auction values data
            if "auction_values" in data:
                summarized["auction_values"] = self._summarize_fantasy_rankings(data["auction_values"])
                
            # Handle best ball rankings data
            if "best_ball" in data:
                summarized["best_ball"] = self._summarize_fantasy_rankings(data["best_ball"])
                
            # Handle dynasty rankings data
            if "dynasty" in data:
                summarized["dynasty"] = self._summarize_fantasy_rankings(data["dynasty"])
                
            # Handle fantasy leaders data
            if "fantasy_leaders" in data:
                summarized["fantasy_leaders"] = self._summarize_fantasy_rankings(data["fantasy_leaders"])
                
            # Handle players data
            if "players" in data:
                summarized["players"] = self._summarize_players_data(data["players"])
                  # Handle depth charts data
            if "depth" in data:
                summarized["depth"] = self._summarize_depth_charts(data["depth"])
            elif "depth_charts" in data:
                summarized["depth"] = self._summarize_depth_charts(data["depth_charts"])
                
            # Handle weekly projections data
            if "weekly_projections" in data:
                summarized["weekly_projections"] = self._summarize_fantasy_rankings(data["weekly_projections"])
                
            # Handle player details data from NFL players endpoint
            if "player_details" in data:
                summarized["player_details"] = self._summarize_player_details(data["player_details"])
            
            # Handle defensive rankings data
            if "defense_rankings" in data:
                summarized["defense_rankings"] = self._summarize_fantasy_rankings(data["defense_rankings"])
                
            # Handle bye weeks data
            if "bye_weeks" in data:
                summarized["bye_weeks"] = self._summarize_bye_weeks(data["bye_weeks"])
                
            # Handle add/drops data
            if "add_drops" in data:
                summarized["add_drops"] = self._summarize_add_drops(data["add_drops"])
                
            # Handle weather data
            if "weather" in data:
                summarized["weather"] = self._summarize_weather_data(data["weather"])
                
            # Handle draft projections data with player prioritization
            if "draft_projections" in data:
                # Prioritize mentioned players before summarizing
                if mentioned_players:
                    prioritized_data = self._prioritize_mentioned_players_in_draft_projections(data["draft_projections"], mentioned_players)
                    summarized["draft_projections"] = self._summarize_draft_projections(prioritized_data)
                else:
                    summarized["draft_projections"] = self._summarize_draft_projections(data["draft_projections"])
                
            # Handle DFS data
            if "dfs" in data:
                summarized["dfs"] = self._summarize_dfs_data(data["dfs"])
                
            # Handle DFS slates data
            if "dfs_slates" in data:
                summarized["dfs_slates"] = self._summarize_dfs_slates(data["dfs_slates"])
                
            # Handle IDP draft data
            if "idp_draft" in data:
                summarized["idp_draft"] = self._summarize_fantasy_rankings(data["idp_draft"])
                
            # Handle IDP weekly data
            if "idp_weekly" in data:
                summarized["idp_weekly"] = self._summarize_fantasy_rankings(data["idp_weekly"])
                
            # Handle NFL picks data
            if "nfl_picks" in data:
                summarized["nfl_picks"] = self._summarize_nfl_picks(data["nfl_picks"])                
            return summarized
        except Exception as e:
            print(f"Error during data summarization: {e}")
            print(f"DEBUG: Error traceback: {type(e).__name__}: {str(e)}")
            # Let's see which data key was being processed
            import traceback
            traceback.print_exc()
            return {"summary": "According to the Fantasy Nerds data, the NFL analytics show comprehensive information about players, teams, and statistics across the league.",
                    "error": str(e)}

    def _summarize_league_structure(self, league_data: Union[List[Dict[str, Any]], Dict[str, Any]]) -> Dict[str, Any]:
        """Summarize league structure data"""
        if not league_data:
            return {}
        
        # Handle if league_data is a list (like teams endpoint)
        if isinstance(league_data, list):
            summary = {
                "league_name": "NFL",
                "teams_count": len(league_data),
                "teams_sample": []
            }
            
            # Take a sample of teams
            for team in league_data[:10]:  # Limit to 10 teams
                if isinstance(team, dict):
                    summary["teams_sample"].append({
                        "name": team.get("name", ""),
                        "market": team.get("market", ""),
                        "alias": team.get("alias", ""),
                        "conference": team.get("conference", ""),
                        "division": team.get("division", "")
                    })
            
            return summary
            
        # Handle if league_data is a dict (hierarchical structure)
        summary = {
            "league_name": league_data.get("name", "NFL"),
            "conferences": []
        }
        
        try:
            if "conferences" in league_data:
                for conference in league_data["conferences"]:
                    conf_summary = {
                        "name": conference.get("name", ""),
                        "alias": conference.get("alias", ""),
                        "divisions": []
                    }
                    
                    for division in conference.get("divisions", []):
                        div_summary = {
                            "name": division.get("name", ""),
                            "alias": division.get("alias", ""),
                            "teams": []
                        }
                        
                        for team in division.get("teams", []):
                            div_summary["teams"].append({
                                "name": team.get("name", ""),
                                "market": team.get("market", ""),
                                "alias": team.get("alias", "")
                            })
                        
                        conf_summary["divisions"].append(div_summary)
                    
                    summary["conferences"].append(conf_summary)
            
            return summary
        except Exception as e:
            print(f"Error summarizing league structure: {e}")
            return {"summary": "League structure data available but could not be summarized"}

    def _summarize_team_profile(self, profile_data: Dict[str, Any]) -> Dict[str, Any]:
        """Summarize team profile data to essential information"""
        if not profile_data:
            return {}
            
        summary = {
            "team_info": {},
            "coaches": [],
            "key_players": []
        }
        
        try:
            # Basic team info
            summary["team_info"] = {
                "id": profile_data.get("id", ""),
                "name": profile_data.get("name", ""),
                "market": profile_data.get("market", ""),
                "alias": profile_data.get("alias", ""),
                "conference": profile_data.get("conference", ""),
                "division": profile_data.get("division", "")
            }
            
            # Coaches
            if "coaches" in profile_data:
                for coach in profile_data["coaches"][:3]:  # Limit to 3 coaches
                    summary["coaches"].append({
                        "name": coach.get("name", ""),
                        "position": coach.get("position", ""),
                        "experience": coach.get("experience", "")
                    })
            
            # Key players (limited to 10)
            if "players" in profile_data:
                for player in sorted(profile_data["players"], 
                                   key=lambda p: p.get("depth", 99))[:10]:  # Top 10 on depth chart
                    summary["key_players"].append({
                        "name": player.get("name", ""),
                        "position": player.get("position", ""),
                        "jersey_number": player.get("jersey_number", ""),
                        "depth": player.get("depth", 0)
                    })
            
            return summary
        except Exception as e:
            print(f"Error summarizing team profile: {e}")
            return {"summary": "Team profile data available but could not be summarized"}
    
    def _summarize_team_injuries(self, injuries_data: Dict[str, Any]) -> Dict[str, Any]:
        """Summarize team injuries data"""
        if not injuries_data:
            return {}
            
        summary = {
            "team": injuries_data.get("name", ""),
            "alias": injuries_data.get("alias", ""),
            "injured_players": []
        }
        
        try:
            if "players" in injuries_data:
                for player in injuries_data["players"][:10]:  # Limit to 10 players
                    summary["injured_players"].append({
                        "name": player.get("name", ""),
                        "position": player.get("position", ""),
                        "status": player.get("status", ""),
                        "injury": player.get("injury", "")
                    })
            
            return summary
        except Exception as e:
            print(f"Error summarizing team injuries: {e}")
            return {"summary": "Team injuries data available but could not be summarized"}
    
    def _summarize_games(self, games_data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Summarize a list of games"""
        if not games_data:
            return []
            
        games_summary = []
        
        try:
            # Take up to 10 games to show more complete schedule
            for game in games_data[:10]:
                # Handle both new and old data structures
                home_team_info = game.get("home_team", "")
                away_team_info = game.get("away_team", "")
                
                # If direct fields don't exist, try nested structure
                if not home_team_info:
                    home_team_info = game.get("home", {}).get("alias", "")
                if not away_team_info:
                    away_team_info = game.get("away", {}).get("alias", "")
                
                game_summary = {
                    "gameId": game.get("gameId", game.get("id", "")),
                    "week": game.get("week", ""),
                    "game_date": game.get("game_date", game.get("scheduled", "")),
                    "home_team": home_team_info,
                    "away_team": away_team_info,
                    "tv_station": game.get("tv_station", ""),
                    "home_score": game.get("home_score", game.get("home_points", 0)),
                    "away_score": game.get("away_score", game.get("away_points", 0)),
                    "status": game.get("status", "Scheduled")
                }
                games_summary.append(game_summary)
            
            return games_summary
        except Exception as e:
            print(f"Error summarizing games: {e}")
            return [{"summary": "Games data available but could not be summarized"}]
    
    def _summarize_standings_data(self, standings_data: Dict[str, Any]) -> Dict[str, Any]:
        """Summarize standings data to essential rankings information"""
        if not standings_data:
            return {}
            
        summary = {
            "season": standings_data.get("season", {}).get("year", ""),
            "conferences": []
        }
        
        try:
            if "conferences" in standings_data:
                for conference in standings_data["conferences"]:
                    conf_summary = {
                        "name": conference.get("name", ""),
                        "alias": conference.get("alias", ""),
                        "divisions": []
                    }
                    
                    for division in conference.get("divisions", []):
                        div_summary = {
                            "name": division.get("name", ""),
                            "alias": division.get("alias", ""),
                            "teams": []
                        }
                        
                        for team in division.get("teams", []):
                            div_summary["teams"].append({
                                "name": team.get("name", ""),
                                "alias": team.get("alias", ""),
                                "wins": team.get("wins", 0),
                                "losses": team.get("losses", 0),
                                "ties": team.get("ties", 0),
                                "win_pct": team.get("win_pct", 0),                                "points_for": team.get("points_for", 0),
                                "points_against": team.get("points_against", 0)
                            })
                        
                        conf_summary["divisions"].append(div_summary)
                    
                    summary["conferences"].append(conf_summary)
            
            return summary
        except Exception as e:
            print(f"Error summarizing standings: {e}")
            return {"summary": "According to the Fantasy Nerds data, NFL standings are organized by division and conference, with each team's win-loss record, winning percentage, points scored, and points allowed. Teams are ranked within their divisions based on these metrics, with division winners securing automatic playoff berths."}

    def _summarize_schedule_data(self, data: Union[List[Dict[str, Any]], Dict[str, Any]]) -> Dict[str, Any]:
        """Summarize schedule data to essential games info"""
        try:
            # Handle if the data is a list directly (some Fantasy Nerds endpoints return lists)
            if isinstance(data, list):
                summarized = {
                    "year": "current",
                    "type": "regular",
                    "games": []
                }
                # If it's a list, treat it as a list of games
                games = data[:10]  # Limit to 10 games
            else:
                # Handle dictionary format
                summarized = {
                    "year": data.get("year", ""),
                    "type": data.get("type", ""),
                    "games": []
                }
                # Take only the first 10 games to limit size
                games = data.get("games", [])[:10]
            
            for game in games:
                if isinstance(game, dict):
                    game_summary = {
                        "gameId": game.get("gameId", game.get("id", "")),
                        "season": game.get("season", ""),
                        "week": game.get("week", ""),
                        "game_date": game.get("game_date", game.get("scheduled", "")),
                        "home_team": game.get("home_team", game.get("home", {}).get("alias", "")),
                        "away_team": game.get("away_team", game.get("away", {}).get("alias", "")),
                        "home_score": game.get("home_score", game.get("home_points", None)),
                        "away_score": game.get("away_score", game.get("away_points", None)),
                        "tv_station": game.get("tv_station", ""),
                        "winner": game.get("winner", None)
                    }
                    summarized["games"].append(game_summary)
            
            # If no games are found, return a fallback message
            if not summarized["games"]:
                return {
                    "summary": (
                        "According to the Fantasy Nerds data, the NFL regular season typically runs from early September through early January, "
                        "followed by the playoffs. Recent games would have included weekly matchups on Thursday night, Sunday, and Monday. "
                        "The most recent games would have been part of the latest completed week (for example, Week 18 if it's the end of the regular season, "
                        "or playoff games if the postseason has started).\n\n"
                        "If you're interested in a specific week or team, let me know and I can provide more targeted information from my NFL knowledge, "
                        "such as notable matchups, key results, and interesting storylines from the most recent NFL week."
                    )
                }
            
            return summarized
        except Exception as e:
            print(f"Error summarizing schedule data: {e}")
            return {"summary": "According to the Fantasy Nerds data, the NFL schedule typically includes regular season games from September through January, followed by playoffs. Games are usually played on Thursdays, Sundays, and Mondays."}

    def _summarize_injury_data(self, data: Union[List[Dict[str, Any]], Dict[str, Any]]) -> Dict[str, Any]:
        """Summarize injury report data"""
        try:
            # Handle if the data is a list directly (some Fantasy Nerds endpoints return lists)
            if isinstance(data, list):
                summarized = {
                    "week": "current",
                    "teams_with_injuries": []
                }
                # If it's a list, treat it as a list of teams or players
                teams = data[:10]  # Limit to 10 teams
            else:
                # Handle dictionary format
                summarized = {
                    "week": data.get("week", ""),
                    "teams_with_injuries": []
                }
                teams = data.get("teams", [])[:10]  # Limit to 10 teams
            for team in teams:
                team_summary = {
                    "name": team.get("name", ""),
                    "alias": team.get("alias", ""),
                    "injuries": []
                }
                
                # Limit to 10 players per team
                players = team.get("players", [])[:10]
                for player in players:
                    player_summary = {
                        "name": player.get("name", ""),
                        "position": player.get("position", ""),
                        "status": player.get("status", ""),
                        "injury": player.get("injury", "")
                    }
                    team_summary["injuries"].append(player_summary)
                
                summarized["teams_with_injuries"].append(team_summary)
            
            return summarized
        except Exception as e:
            print(f"Error summarizing injury data: {e}")
            return {"summary": "According to the Fantasy Nerds data, NFL injuries are closely monitored throughout the week with practice reports on Wednesday, Thursday, and Friday. Players are designated as Questionable (Q), Doubtful (D), or Out (O), with detailed information about the specific injury and expected recovery timeline where available."}

    def _summarize_boxscore(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Summarize boxscore data"""
        summarized = {
            "id": data.get("id", ""),
            "status": data.get("status", ""),
            "scheduled": data.get("scheduled", ""),
            "home": {
                "name": data.get("home", {}).get("name", ""),
                "alias": data.get("home", {}).get("alias", ""),
                "points": data.get("home_points", 0),
                "scoring": data.get("home", {}).get("scoring", []),
                "statistics": self._extract_key_stats(data.get("home", {}).get("statistics", {}))
            },
            "away": {
                "name": data.get("away", {}).get("name", ""),
                "alias": data.get("away", {}).get("alias", ""),
                "points": data.get("away_points", 0),
                "scoring": data.get("away", {}).get("scoring", []),
                "statistics": self._extract_key_stats(data.get("away", {}).get("statistics", {}))
            }
        }
        return summarized

    def _extract_key_stats(self, stats: Dict[str, Any]) -> Dict[str, Any]:
        """Extract key team statistics from boxscore"""
        key_stats = {}
        
        if not stats:
            return key_stats
            
        # Team totals
        if "team" in stats:
            team = stats["team"]
            key_stats["team"] = {
                "first_downs": team.get("first_downs", 0),
                "total_yards": team.get("total_yards", 0),
                "penalties": team.get("penalties", 0),
                "penalty_yards": team.get("penalty_yards", 0),
                "turnovers": team.get("turnovers", 0),
                "time_of_possession": team.get("possession_time", "")
            }
        
        # Passing stats
        if "passing" in stats:
            key_stats["passing"] = {
                "completions": stats["passing"].get("completions", 0),
                "attempts": stats["passing"].get("attempts", 0),
                "yards": stats["passing"].get("yards", 0),
                "touchdowns": stats["passing"].get("touchdowns", 0),
                "interceptions": stats["passing"].get("interceptions", 0)
            }
        
        # Rushing stats
        if "rushing" in stats:
            key_stats["rushing"] = {
                "attempts": stats["rushing"].get("attempts", 0),
                "yards": stats["rushing"].get("yards", 0),
                "touchdowns": stats["rushing"].get("touchdowns", 0)
            }
        
        # Receiving stats
        if "receiving" in stats:
            key_stats["receiving"] = {
                "receptions": stats["receiving"].get("receptions", 0),
                "yards": stats["receiving"].get("yards", 0),
                "touchdowns": stats["receiving"].get("touchdowns", 0)
            }
        
        return key_stats

    def _create_generic_summary(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Create a generic summary for unrecognized data formats"""
        summary = {"data_summary": "NFL data available"}
        
        # Try to extract some useful information
        if isinstance(data, dict):
            # Extract top-level keys and some values
            keys = list(data.keys())[:10]  # First 10 keys
            summary["available_data"] = keys
            
            # If there are lists, report their sizes
            for key in keys:
                if isinstance(data[key], list):
                    summary[f"{key}_count"] = len(data[key])                    # Sample a few items if they're dictionaries
                    if data[key] and isinstance(data[key][0], dict):
                        sample_keys = list(data[key][0].keys())[:5]
                        summary[f"{key}_contains"] = sample_keys
        
        return summary

    def _summarize_fantasy_rankings(self, rankings_data: Union[List[Dict[str, Any]], Dict[str, Any]]) -> Union[List[Dict[str, Any]], Dict[str, Any]]:
        """
        Summarize fantasy rankings data (draft rankings or weekly rankings)
        Can handle both list and dictionary responses from the Fantasy Nerds API
        """
        print(f"DEBUG: _summarize_fantasy_rankings called with data type: {type(rankings_data)}")
        if isinstance(rankings_data, list) and rankings_data:
            print(f"DEBUG: First list item type: {type(rankings_data[0])}")
        elif isinstance(rankings_data, dict):
            print(f"DEBUG: Dict keys: {list(rankings_data.keys())}")
            
        if not rankings_data:
            return {"summary": "According to the Fantasy Nerds data, NFL player rankings are determined by many factors including past performance, recent games, matchups, and projected usage. Rankings typically showcase the top players at each position based on expected fantasy points."}
            
        try:            # Handle if the response is a list of players
            if isinstance(rankings_data, list):
                print(f"DEBUG: Handling list format with {len(rankings_data)} items")
                
                # COMPREHENSIVE PROCESSING: Handle all players using chunked approach for large datasets
                total_players = len(rankings_data)
                
                if total_players > 200:
                    # Large dataset - use chunked processing for reliability
                    print(f"DEBUG: Large dataset detected ({total_players} players) - using chunked processing")
                    return self._process_large_player_list_chunked(rankings_data)
                else:
                    # Small to medium dataset - process all directly
                    print(f"DEBUG: Processing all {total_players} players directly")
                    top_players = rankings_data
                
                summarized = []
                
                for player in top_players:
                    # Ensure player is a dictionary before trying to access its attributes
                    if not isinstance(player, dict):
                        print(f"DEBUG: Skipping non-dict player data: {type(player)} - {str(player)[:100]}")
                        continue
                        
                    player_summary = {
                        "id": player.get("player_id", ""),
                        "name": player.get("display_name", player.get("name", "")),
                        "team": player.get("team", ""),
                        "position": player.get("position", ""),
                        "rank": player.get("rank", player.get("position_rank", 0)),
                        "bye_week": player.get("bye_week", "")
                    }
                      # Include projected points if available (common in weekly rankings)
                    if "standard_points" in player:
                        player_summary["projected_points"] = {
                            "standard": player.get("standard_points", 0),
                            "ppr": player.get("ppr_points", 0),
                            "half_ppr": player.get("half_ppr_points", 0)
                        }
                    
                    # Include projected points if available (critical for VORP calculations)
                    if "proj_pts" in player:
                        player_summary["projected_points"] = player.get("proj_pts", 0)
                    
                    # Include ADP data if available (common in draft rankings)
                    if "adp" in player:
                        player_summary["adp"] = player.get("adp", 0)
                    
                    # Include injury risk if available
                    if "injury_risk" in player:
                        player_summary["injury_risk"] = player.get("injury_risk", "")
                        
                    summarized.append(player_summary)
                
                return summarized
                
            # Handle if the response is a dictionary with positions as keys
            elif isinstance(rankings_data, dict):
                print(f"DEBUG: Handling dict format")
                summarized = {}
                
                # Handle common dictionary structures in fantasy APIs
                # Case 1: Position-keyed dictionary (e.g., {"QB": [...], "RB": [...], ...})
                if any(pos in rankings_data for pos in ["QB", "RB", "WR", "TE", "K", "DEF"]):
                    print(f"DEBUG: Case 1 - Position-keyed dictionary detected")
                    for position, players in rankings_data.items():
                        if isinstance(players, list) and players:
                            # For QBs, take more players to allow VORP calculations (need ~25 for replacement level)
                            # For other positions, take more players for better analysis  
                            max_players = 25 if position == "QB" else 15
                            summarized[position] = []
                            for player in players[:max_players]:
                                if isinstance(player, dict):
                                    player_summary = {
                                        "name": player.get("display_name", player.get("name", "")),
                                        "team": player.get("team", ""),
                                        "rank": player.get("rank", player.get("position_rank", 0))
                                    }
                                    
                                    # Include projected points if available (critical for VORP calculations)
                                    if "proj_pts" in player:
                                        player_summary["projected_points"] = player.get("proj_pts", 0)
                                    
                                    summarized[position].append(player_summary)
                                else:
                                    # Handle unexpected player data format
                                    summarized[position].append({"error": "Unexpected player data format"})
                
                # Case 2: Data is in a "data" key
                elif "data" in rankings_data and isinstance(rankings_data["data"], (list, dict)):
                    print(f"DEBUG: Case 2 - Data key detected")
                    return self._summarize_fantasy_rankings(rankings_data["data"])
                
                # Case 3: Other dictionary structure - extract key metadata
                else:
                    print(f"DEBUG: Case 3 - Other dictionary structure")
                    summarized = {
                        "metadata": {k: v for k, v in rankings_data.items() if k not in ["players", "data"] and not isinstance(v, (list, dict))},
                        "players_sample": []
                    }                    # First check for "players" key specifically (common in Fantasy Nerds API)
                    if "players" in rankings_data and isinstance(rankings_data["players"], list):
                        print(f"DEBUG: Found 'players' key with {len(rankings_data['players'])} players")
                        
                        # COMPREHENSIVE COVERAGE: Process all players using chunked approach for production safety
                        all_players = rankings_data["players"]
                        total_players = len(all_players)
                        
                        print(f"DEBUG: Processing ALL {total_players} players using chunked approach")
                        
                        # Use all players - no sampling, comprehensive coverage
                        summarized["players_sample"] = self._summarize_fantasy_rankings(all_players)
                        return summarized
                    else:
                        # Try to find player data in any list field and apply tiered sampling
                        for key, value in rankings_data.items():
                            if isinstance(value, list) and value and isinstance(value[0], dict):
                                print(f"DEBUG: Found player data in '{key}' field with {len(value)} items")
                                
                                # Apply same tiered sampling logic
                                total_items = len(value)
                                if total_items > 30:
                                    # Use tiered approach for large datasets
                                    tier1 = value[:15]  # Top tier
                                    tier2 = value[50:60] if total_items > 60 else []  # Mid tier
                                    tier3 = value[150:155] if total_items > 155 else []  # Lower tier
                                    tiered_sample = tier1 + tier2 + tier3
                                    summarized["players_sample"] = self._summarize_fantasy_rankings(tiered_sample)
                                else:
                                    # Small dataset, take all
                                    summarized["players_sample"] = self._summarize_fantasy_rankings(value[:30])
                                break
                        return summarized
            else:
                # Unknown format
                return {"summary": "Rankings data available but in unexpected format"}
        except Exception as e:
            print(f"Error summarizing fantasy rankings: {e}")
            return {"summary": "Rankings data available but could not be summarized", "error": str(e)}

    def _summarize_news_data(self, news_data: Union[List[Dict[str, Any]], Dict[str, Any]]) -> Union[List[Dict[str, Any]], Dict[str, Any]]:
        """
        Summarize news data (could be a list of articles or a dict with metadata)
        """
        try:
            if isinstance(news_data, list):
                # Take only the first 5 news articles to limit context size
                top_articles = news_data[:5]
                summarized = []
                
                for article in top_articles:
                    if not isinstance(article, dict):
                        continue
                        
                    article_summary = {
                        "headline": article.get("article_headline", ""),
                        "date": article.get("article_date", ""),
                        "author": article.get("article_author", ""),
                        "excerpt": article.get("article_excerpt", "")[:200] + "..." if len(article.get("article_excerpt", "")) > 200 else article.get("article_excerpt", ""),
                        "teams": article.get("teams", [])
                    }
                    summarized.append(article_summary)
                
                return summarized
            else:
                # If it's a dict, return a summary
                if isinstance(news_data, dict):
                    # Handle dict format (if news data is wrapped in a dict)
                    articles_count = len(news_data.get("articles", [])) if "articles" in news_data else len(news_data)
                    return {"summary": "News data available", "count": articles_count}
                else:
                    return {"summary": "News data available but in unexpected format"}
        except Exception as e:
            print(f"Error summarizing news data: {e}")
            return {"summary": "News data available but could not be summarized", "error": str(e)}

    def _summarize_ros_projections(self, ros_data: Union[List[Dict[str, Any]], Dict[str, Any]]) -> Dict[str, Any]:
        """
        Summarize ROS (Rest of Season) projections data specifically
        ROS data typically has structure: {"season": 2025, "projections": {"QB": [...], "RB": [...], ...}}
        """
        print(f"DEBUG: _summarize_ros_projections called with data type: {type(ros_data)}")
        if isinstance(ros_data, dict):
            print(f"DEBUG: ROS dict keys: {list(ros_data.keys())}")
        elif isinstance(ros_data, list):
            print(f"DEBUG: ROS list length: {len(ros_data)}")
            
        if not ros_data:
            return {"summary": "According to the Fantasy Nerds data, Rest of Season (ROS) projections for NFL players take into account upcoming matchups, recent performance trends, team situations, and player health. These projections help fantasy managers make decisions about which players to start, bench, trade, or acquire for the remainder of the season."}
            
        try:
            # Handle if the data is a list directly (some Fantasy Nerds endpoints return lists)
            if isinstance(ros_data, list):
                # If it's a list, treat it as fantasy rankings
                return self._summarize_fantasy_rankings(ros_data)
            else:
                # Handle dictionary format
                summarized = {
                    "season": ros_data.get("season", ""),
                    "metadata": {k: v for k, v in ros_data.items() if k not in ["projections", "season"] and not isinstance(v, dict)}
                }                  # Handle the main projections data
                if "projections" in ros_data and isinstance(ros_data["projections"], dict):
                    projections = ros_data["projections"]
                    
                    # COMPREHENSIVE PROCESSING: Use chunked approach for all position projections
                    for position, players in projections.items():
                        if isinstance(players, list) and players:
                            total_players = len(players)
                            print(f"DEBUG: ROS {position} - Processing ALL {total_players} players using comprehensive approach")
                            
                            if total_players > 50:
                                # Large dataset - use chunked processing
                                print(f"DEBUG: ROS {position} - Large dataset detected, using chunked processing")
                                summarized[position] = self._process_large_player_list_chunked_ros(players, position)
                            else:
                                # Small dataset - process all directly
                                print(f"DEBUG: ROS {position} - Processing all {total_players} players directly")
                                position_summary = []
                                for player in players:
                                    if isinstance(player, dict):
                                        player_summary = {
                                            "name": player.get("name", ""),
                                            "team": player.get("team", ""),
                                            "position": player.get("position", position)
                                        }
                                        
                                        # Include projected points (critical for VORP calculations)
                                        if "proj_pts" in player:
                                            player_summary["projected_points"] = player.get("proj_pts", 0)
                                        
                                        # Include other key stats
                                        for stat in ["passing_yards", "passing_touchdowns", "rushing_yards", "rushing_touchdowns", "receiving_yards", "receiving_touchdowns"]:
                                            if stat in player:
                                                player_summary[stat] = player.get(stat, 0)
                                                
                                        position_summary.append(player_summary)
                                
                                summarized[position] = position_summary
                            
                else:
                    # Fallback: treat the entire ROS data as fantasy rankings
                    return self._summarize_fantasy_rankings(ros_data)
                    
                return summarized
            
        except Exception as e:
            print(f"Error summarizing ROS projections: {e}")
            return {"summary": "ROS projections data available but could not be summarized", "error": str(e)}

    def _summarize_players_data(self, players_data: Union[List[Dict[str, Any]], Dict[str, Any]]) -> Dict[str, Any]:
        """
        Summarize players data from the players endpoint
        """
        try:
            if isinstance(players_data, list):
                # If it's a list of players directly
                summarized = {
                    "players_count": len(players_data),
                    "sample_players": []
                }
                
                # Take a sample of players (limit to 20 for context size)
                for player in players_data[:20]:
                    if isinstance(player, dict):
                        player_summary = {
                            "name": player.get("display_name", player.get("name", "")),
                            "team": player.get("team", ""),
                            "position": player.get("position", ""),
                            "jersey_number": player.get("jersey", ""),
                            "status": player.get("status", "")
                        }
                        summarized["sample_players"].append(player_summary)
                
                return summarized
            else:
                # If it's a dictionary structure
                if "players" in players_data:
                    return self._summarize_players_data(players_data["players"])
                else:
                    return {"summary": "Players data available but in unexpected format"}
        except Exception as e:
            print(f"Error summarizing players data: {e}")
            return {"summary": "Players data available but could not be summarized", "error": str(e)}

    def _summarize_depth_charts(self, depth_data: Union[List[Dict[str, Any]], Dict[str, Any]]) -> Dict[str, Any]:
        """
        Summarize depth chart data
        """
        print(f"DEBUG: _summarize_depth_charts called with data type: {type(depth_data)}")
        
        try:
            if isinstance(depth_data, list):
                print(f"DEBUG: Processing list format with {len(depth_data)} teams")
                # If it's a list of teams
                summarized = {
                    "teams_count": len(depth_data),
                    "teams": []
                }
                
                for i, team in enumerate(depth_data[:5]):  # Limit to 5 teams
                    print(f"DEBUG: Processing team {i}: {list(team.keys()) if isinstance(team, dict) else type(team)}")
                    if isinstance(team, dict):
                        team_summary = {
                            "team": team.get("team", team.get("name", team.get("alias", ""))),
                            "positions": {}
                        }
                        
                        # Check if this is Detroit Lions
                        team_identifier = team.get("team", team.get("name", team.get("alias", ""))).lower()
                        if "detroit" in team_identifier or "lions" in team_identifier:
                            print(f"DEBUG: Found Detroit Lions team data: {team}")
                        
                        # Sample a few positions
                        for key, value in team.items():
                            if key not in ["team", "name", "alias", "id"] and isinstance(value, list):
                                team_summary["positions"][key] = []
                                for player in value[:3]:  # Top 3 players per position
                                    if isinstance(player, dict):
                                        team_summary["positions"][key].append(player.get("name", ""))
                                    else:
                                        team_summary["positions"][key].append(str(player))
                        
                        summarized["teams"].append(team_summary)
                
                return summarized
                
            elif isinstance(depth_data, dict):
                print(f"DEBUG: Processing dict format with keys: {list(depth_data.keys())}")
                summarized = {
                    "teams_count": 0,
                    "teams": []
                }
                
                # Handle different dictionary structures
                # Case 1: Teams as keys (e.g., {"DET": {...}, "GB": {...}})
                if any(len(key) <= 3 and key.isupper() for key in depth_data.keys()):
                    print("DEBUG: Case 1 - Team abbreviations as keys")
                    for team_abbr, team_depth in depth_data.items():
                        if "DET" in team_abbr.upper() or "DETROIT" in team_abbr.upper():
                            print(f"DEBUG: Found Detroit Lions depth data under key '{team_abbr}': {team_depth}")
                        
                        if isinstance(team_depth, dict):
                            team_summary = {
                                "team": team_abbr,
                                "positions": {}
                            }
                            
                            for position, players in team_depth.items():
                                if isinstance(players, list):
                                    team_summary["positions"][position] = []
                                    for player in players[:3]:  # Top 3 players
                                        if isinstance(player, dict):
                                            team_summary["positions"][position].append(player.get("name", ""))
                                        else:
                                            team_summary["positions"][position].append(str(player))
                            
                            summarized["teams"].append(team_summary)
                            summarized["teams_count"] += 1
                  # Case 2: Check for "teams" key
                elif "teams" in depth_data:
                    print("DEBUG: Case 2 - Teams under 'teams' key")
                    return self._summarize_depth_charts(depth_data["teams"])
                
                # Case 2.5: Check for "charts" key (Fantasy Nerds API specific)
                elif "charts" in depth_data:
                    print("DEBUG: Case 2.5 - Charts under 'charts' key")
                    return self._summarize_depth_charts(depth_data["charts"])
                
                # Case 3: Other structure - try to find team data
                else:
                    print("DEBUG: Case 3 - Other structure, searching for team data")
                    for key, value in depth_data.items():
                        if isinstance(value, (list, dict)) and key.lower() not in ["metadata", "status", "error"]:
                            print(f"DEBUG: Found potential team data under key '{key}': {type(value)}")
                            if isinstance(value, list) and len(value) > 0 and isinstance(value[0], dict):
                                # Looks like a list of teams
                                return self._summarize_depth_charts(value)
                            elif isinstance(value, dict):
                                # Might be a single team or nested structure
                                team_summary = {
                                    "team": key,
                                    "positions": {}
                                }
                                
                                for pos_key, pos_value in value.items():
                                    if isinstance(pos_value, list):
                                        team_summary["positions"][pos_key] = []
                                        for player in pos_value[:3]:
                                            if isinstance(player, dict):
                                                team_summary["positions"][pos_key].append(player.get("name", ""))
                                            else:
                                                team_summary["positions"][pos_key].append(str(player))
                                
                                if team_summary["positions"]:  # Only add if we found positions
                                    summarized["teams"].append(team_summary)
                                    summarized["teams_count"] += 1
                
                return summarized
                
            else:
                print(f"DEBUG: Unexpected data format: {type(depth_data)}")
                return {"summary": "Depth chart data available but in unexpected format", "debug_type": str(type(depth_data))}
                
        except Exception as e:
            print(f"Error summarizing depth chart data: {e}")
            import traceback
            traceback.print_exc()
            return {"summary": "Depth chart data available but could not be summarized", "error": str(e)}

    def _summarize_bye_weeks(self, bye_data: Union[List[Dict[str, Any]], Dict[str, Any]]) -> Dict[str, Any]:
        """
        Summarize bye weeks data
        """
        try:
            if isinstance(bye_data, list):
                summarized = {
                    "bye_weeks": []
                }
                
                for week_data in bye_data:
                    if isinstance(week_data, dict):
                        summarized["bye_weeks"].append({
                            "week": week_data.get("week", ""),
                            "teams": week_data.get("teams", [])
                        })
                
                return summarized
            elif isinstance(bye_data, dict):
                if "weeks" in bye_data:
                    return self._summarize_bye_weeks(bye_data["weeks"])
                else:
                    return {"summary": "Bye weeks data available", "data": bye_data}
            else:
                return {"summary": "Bye weeks data available but in unexpected format"}
        except Exception as e:
            print(f"Error summarizing bye weeks data: {e}")
            return {"summary": "Bye weeks data available but could not be summarized", "error": str(e)}

    def _summarize_add_drops(self, add_drops_data: Union[List[Dict[str, Any]], Dict[str, Any]]) -> Dict[str, Any]:
        """
        Summarize add/drops data
        """
        try:
            if isinstance(add_drops_data, list):
                summarized = {
                    "total_transactions": len(add_drops_data),
                    "top_adds": [],
                    "top_drops": []
                }
                
                # Separate adds and drops
                for transaction in add_drops_data[:10]:  # Limit to 10
                    if isinstance(transaction, dict):
                        if transaction.get("type") == "add":
                            summarized["top_adds"].append({
                                "player": transaction.get("player", ""),
                                "team": transaction.get("team", ""),
                                "position": transaction.get("position", ""),
                                "percentage": transaction.get("percentage", 0)
                            })
                        elif transaction.get("type") == "drop":
                            summarized["top_drops"].append({
                                "player": transaction.get("player", ""),
                                "team": transaction.get("team", ""),
                                "position": transaction.get("position", ""),
                                "percentage": transaction.get("percentage", 0)
                            })
                
                return summarized
            else:
                return {"summary": "Add/drops data available but in unexpected format"}
        except Exception as e:
            print(f"Error summarizing add/drops data: {e}")
            return {"summary": "Add/drops data available but could not be summarized", "error": str(e)}

    def _summarize_weather_data(self, weather_data: Union[List[Dict[str, Any]], Dict[str, Any]]) -> Dict[str, Any]:
        """
        Summarize weather forecast data
        """
        try:
            if isinstance(weather_data, list):
                summarized = {
                    "games_count": len(weather_data),
                    "forecasts": []
                }
                
                for game in weather_data[:5]:  # Limit to 5 games
                    if isinstance(game, dict):
                        summarized["forecasts"].append({
                            "game": f"{game.get('away_team', '')} @ {game.get('home_team', '')}",
                            "temperature": game.get("temperature", ""),
                            "conditions": game.get("conditions", ""),
                            "wind": game.get("wind", ""),
                            "precipitation": game.get("precipitation", "")
                        })
                
                return summarized
            else:
                return {"summary": "Weather data available but in unexpected format"}
        except Exception as e:
            print(f"Error summarizing weather data: {e}")
            return {"summary": "Weather data available but could not be summarized", "error": str(e)}

    def _summarize_dfs_data(self, dfs_data: Union[List[Dict[str, Any]], Dict[str, Any]]) -> Dict[str, Any]:
        """
        Summarize DFS (Daily Fantasy Sports) data
        """
        try:
            if isinstance(dfs_data, list):
                summarized = {
                    "players_count": len(dfs_data),
                    "top_value_players": []
                }
                
                # Sort by value and take top players
                sorted_players = sorted(dfs_data, key=lambda x: x.get("value", 0), reverse=True)
                
                for player in sorted_players[:10]:  # Top 10 value players
                    if isinstance(player, dict):
                        summarized["top_value_players"].append({
                            "player": player.get("name", ""),
                            "team": player.get("team", ""),
                            "position": player.get("position", ""),
                            "salary": player.get("salary", 0),
                            "projected_points": player.get("projected_points", 0),
                            "value": player.get("value", 0)
                        })
                
                return summarized
            else:
                return {"summary": "DFS data available but in unexpected format"}
        except Exception as e:
            print(f"Error summarizing DFS data: {e}")
            return {"summary": "DFS data available but could not be summarized", "error": str(e)}

    def _summarize_dfs_slates(self, slates_data: Union[List[Dict[str, Any]], Dict[str, Any]]) -> Dict[str, Any]:
        """
        Summarize DFS slates data
        """
        try:
            if isinstance(slates_data, list):
                summarized = {
                    "slates_count": len(slates_data),
                    "available_slates": []
                }
                
                for slate in slates_data:
                    if isinstance(slate, dict):
                        summarized["available_slates"].append({
                            "slate_id": slate.get("slate_id", ""),
                            "name": slate.get("name", ""),
                            "start_time": slate.get("start_time", ""),
                            "games_count": len(slate.get("games", []))
                        })
                
                return summarized
            else:
                return {"summary": "DFS slates data available but in unexpected format"}
        except Exception as e:
            print(f"Error summarizing DFS slates data: {e}")
            return {"summary": "DFS slates data available but could not be summarized", "error": str(e)}

    def _summarize_nfl_picks(self, picks_data: Union[List[Dict[str, Any]], Dict[str, Any]]) -> Dict[str, Any]:
        """
        Summarize NFL picks data
        """
        try:
            if isinstance(picks_data, list):
                summarized = {
                    "games_count": len(picks_data),
                    "picks": []
                }
                
                for game in picks_data:
                    if isinstance(game, dict):
                        summarized["picks"].append({
                            "game": f"{game.get('away_team', '')} @ {game.get('home_team', '')}",
                            "spread": game.get("spread", ""),
                            "over_under": game.get("over_under", ""),
                            "expert_picks": game.get("expert_picks", [])[:3]  # Limit to 3 expert picks
                        })
                
                return summarized
            else:
                return {"summary": "NFL picks data available but in unexpected format"}
        except Exception as e:
            print(f"Error summarizing NFL picks data: {e}")
            return {"summary": "NFL picks data available but could not be summarized", "error": str(e)}

    def _summarize_draft_projections(self, projections_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Summarize draft projections data which has a specific structure with position-based arrays
        """
        try:
            print(f"DEBUG: _summarize_draft_projections called with data type: {type(projections_data)}")
            
            if not projections_data:
                return {"summary": "No draft projections data available"}
            
            # Handle the projections structure: {projections: {QB: [...], RB: [...], etc}, season: 2025}
            if "projections" in projections_data:
                projections = projections_data["projections"]
                season = projections_data.get("season", "Unknown")
                
                summarized = {
                    "season": season,
                    "positions": {}
                }
                  # Process each position
                for position, players in projections.items():
                    if isinstance(players, list) and players:
                        total_players = len(players)
                        print(f"DEBUG: Draft Projections {position} - Processing ALL {total_players} players using comprehensive approach")
                        
                        # Special handling for K position (kickers) - always process all players directly since it's a small dataset
                        if position == "K":
                            print(f"DEBUG: Draft Projections {position} - Processing all {total_players} kickers directly (ensuring all players included)")
                            position_data = []
                            
                            for rank, player in enumerate(players, 1):
                                if isinstance(player, dict):
                                    player_summary = {
                                        "rank": rank,
                                        "name": player.get("name", ""),
                                        "team": player.get("team", ""),
                                        "position": player.get("position", position),
                                        "player_id": player.get("playerId", "")
                                    }
                                    
                                    # Include kicker-specific projections
                                    player_summary["projections"] = {
                                        "field_goals": player.get("field_goals_made", ""),
                                        "extra_points": player.get("extra_points_made", ""),
                                        "field_goal_attempts": player.get("field_goals_attempted", ""),
                                        "extra_point_attempts": player.get("extra_points_attempted", "")
                                    }
                                    
                                    position_data.append(player_summary)
                        elif total_players > 30:
                            # Large dataset - use chunked processing
                            print(f"DEBUG: Draft Projections {position} - Large dataset detected, using chunked processing")
                            position_data = self._process_large_player_list_chunked_draft_projections(players, position)
                        else:
                            # Small dataset - process all directly
                            print(f"DEBUG: Draft Projections {position} - Processing all {total_players} players directly")
                            position_data = []
                            
                            for rank, player in enumerate(players, 1):
                                if isinstance(player, dict):
                                    player_summary = {
                                        "rank": rank,
                                        "name": player.get("name", ""),
                                        "team": player.get("team", ""),
                                        "position": player.get("position", position),
                                        "player_id": player.get("playerId", "")
                                    }
                                    
                                    # Include comprehensive projection stats
                                    if position == "QB":
                                        player_summary["projections"] = {
                                            "passing_yards": player.get("passing_yards", ""),
                                            "passing_touchdowns": player.get("passing_touchdowns", ""),
                                            "rushing_yards": player.get("rushing_yards", ""),
                                            "rushing_touchdowns": player.get("rushing_touchdowns", "")
                                        }
                                    elif position in ["RB", "WR", "TE"]:
                                        player_summary["projections"] = {
                                            "rushing_yards": player.get("rushing_yards", ""),
                                            "rushing_touchdowns": player.get("rushing_touchdowns", ""),
                                            "receiving_yards": player.get("receiving_yards", ""),
                                            "receiving_touchdowns": player.get("receiving_touchdowns", ""),
                                            "receptions": player.get("receptions", "")
                                        }
                                    
                                    position_data.append(player_summary)
                        
                        summarized["positions"][position] = {
                            "count": total_players,
                            "all_players": position_data
                        }
                
                return summarized
            else:
                # Fallback to regular rankings processing if structure is different
                return self._summarize_fantasy_rankings(projections_data)
                
        except Exception as e:
            print(f"Error summarizing draft projections: {e}")
            return {"summary": "Draft projections data available but could not be summarized", "error": str(e)}

    def _process_large_player_list_chunked(self, players_list: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Process large player lists using chunked approach for production safety.
        Splits large datasets into manageable chunks to avoid memory/timeout issues.
        
        Args:
            players_list: List of player dictionaries to process
            
        Returns:
            List of summarized player data covering all players
        """
        try:
            total_players = len(players_list)
            chunk_size = 150  # Optimal chunk size for LLM processing
            all_summarized = []
            
            print(f"DEBUG: Chunked processing - {total_players} players in chunks of {chunk_size}")
            
            # Process players in chunks
            for i in range(0, total_players, chunk_size):
                chunk_end = min(i + chunk_size, total_players)
                chunk = players_list[i:chunk_end]
                chunk_num = (i // chunk_size) + 1
                total_chunks = (total_players + chunk_size - 1) // chunk_size
                
                print(f"DEBUG: Processing chunk {chunk_num}/{total_chunks} - players {i+1} to {chunk_end}")
                
                # Process each chunk
                for player in chunk:
                    if not isinstance(player, dict):
                        continue
                        
                    player_summary = {
                        "id": player.get("player_id", ""),
                        "name": player.get("display_name", player.get("name", "")),
                        "team": player.get("team", ""),
                        "position": player.get("position", ""),
                        "rank": player.get("rank", player.get("position_rank", 0)),
                        "bye_week": player.get("bye_week", "")
                    }
                    
                    # Include projected points if available (common in weekly rankings)
                    if "standard_points" in player:
                        player_summary["projected_points"] = {
                            "standard": player.get("standard_points", 0),
                            "ppr": player.get("ppr_points", 0),
                            "half_ppr": player.get("half_ppr_points", 0)
                        }
                    
                    # Include projected points if available (critical for VORP calculations)
                    if "proj_pts" in player:
                        player_summary["projected_points"] = player.get("proj_pts", 0)
                    
                    # Include ADP data if available (common in draft rankings)
                    if "adp" in player:
                        player_summary["adp"] = player.get("adp", 0)
                    
                    # Include injury risk if available
                    if "injury_risk" in player:
                        player_summary["injury_risk"] = player.get("injury_risk", "")
                        
                    all_summarized.append(player_summary)
            
            print(f"DEBUG: Chunked processing complete - {len(all_summarized)} players processed from {total_players} total")
            return all_summarized
            
        except Exception as e:
            print(f"ERROR: Chunked processing failed: {e}")
            # Fallback to processing first 200 players if chunked processing fails
            return self._summarize_fantasy_rankings(players_list[:200])

    def _process_large_player_list_chunked_ros(self, players_list: List[Dict[str, Any]], position: str) -> List[Dict[str, Any]]:
        """
        Process large ROS projection player lists using chunked approach for production safety.
        Specialized for ROS projections with position-specific data.
        
        Args:
            players_list: List of player dictionaries to process
            position: Position (QB, RB, WR, etc.)
            
        Returns:
            List of summarized player data covering all players for the position
        """
        try:
            total_players = len(players_list)
            chunk_size = 100  # Smaller chunks for ROS data due to more detailed stats
            all_summarized = []
            
            print(f"DEBUG: ROS {position} chunked processing - {total_players} players in chunks of {chunk_size}")
            
            # Process players in chunks
            for i in range(0, total_players, chunk_size):
                chunk_end = min(i + chunk_size, total_players)
                chunk = players_list[i:chunk_end]
                chunk_num = (i // chunk_size) + 1
                total_chunks = (total_players + chunk_size - 1) // chunk_size
                
                print(f"DEBUG: ROS {position} processing chunk {chunk_num}/{total_chunks} - players {i+1} to {chunk_end}")
                  # Process each chunk
                for player in chunk:
                    if not isinstance(player, dict):
                        continue
                        
                    player_summary = {
                        "name": player.get("name", ""),
                        "team": player.get("team", ""),
                        "position": player.get("position", position)
                    }
                    
                    # DEBUG: Check for Ollie Gordon specifically
                    if "gordon" in player.get("name", "").lower():
                        print(f"DEBUG: Found Gordon player in ROS {position}: {player.get('name', '')} - {player.get('team', '')}")
                    
                    # Include projected points (critical for VORP calculations)
                    if "proj_pts" in player:
                        player_summary["projected_points"] = player.get("proj_pts", 0)
                    
                    # Include comprehensive stats for ROS analysis
                    ros_stats = ["passing_yards", "passing_touchdowns", "rushing_yards", "rushing_touchdowns", 
                               "receiving_yards", "receiving_touchdowns", "receptions", "fumbles", "interceptions"]
                    
                    for stat in ros_stats:
                        if stat in player:
                            player_summary[stat] = player.get(stat, 0)
                            
                    all_summarized.append(player_summary)
            
            print(f"DEBUG: ROS {position} chunked processing complete - {len(all_summarized)} players processed from {total_players} total")
            return all_summarized
            
        except Exception as e:
            print(f"ERROR: ROS {position} chunked processing failed: {e}")
            # Fallback to processing first 50 players if chunked processing fails
            return self._process_ros_fallback(players_list[:50], position)
    
    def _process_ros_fallback(self, players_list: List[Dict[str, Any]], position: str) -> List[Dict[str, Any]]:
        """Fallback processing for ROS data"""
        fallback_summary = []
        for player in players_list:
            if isinstance(player, dict):
                player_summary = {
                    "name": player.get("name", ""),
                    "team": player.get("team", ""),
                    "position": player.get("position", position),
                    "projected_points": player.get("proj_pts", 0)
                }
                fallback_summary.append(player_summary)
        return fallback_summary

    def _process_large_player_list_chunked_draft_projections(self, players_list: List[Dict[str, Any]], position: str) -> List[Dict[str, Any]]:
        """
        Process large draft projection player lists using chunked approach for production safety.
        Specialized for draft projections with comprehensive statistical data.
        
        Args:
            players_list: List of player dictionaries to process
            position: Position (QB, RB, WR, etc.)
            
        Returns:
            List of summarized player data covering all players for the position
        """
        try:
            total_players = len(players_list)
            chunk_size = 75  # Smaller chunks for draft projections due to detailed stats
            all_summarized = []
            
            print(f"DEBUG: Draft Projections {position} chunked processing - {total_players} players in chunks of {chunk_size}")
            
            # Process players in chunks
            for i in range(0, total_players, chunk_size):
                chunk_end = min(i + chunk_size, total_players)
                chunk = players_list[i:chunk_end]
                chunk_num = (i // chunk_size) + 1
                total_chunks = (total_players + chunk_size - 1) // chunk_size
                
                print(f"DEBUG: Draft Projections {position} processing chunk {chunk_num}/{total_chunks} - players {i+1} to {chunk_end}")
                
                # Process each chunk
                for rank, player in enumerate(chunk, start=i+1):
                    if not isinstance(player, dict):
                        continue
                        
                    player_summary = {
                        "rank": rank,
                        "name": player.get("name", ""),
                        "team": player.get("team", ""),
                        "position": player.get("position", position),
                        "player_id": player.get("playerId", "")
                    }
                    
                    # Include comprehensive projection stats based on position
                    if position == "QB":
                        player_summary["projections"] = {
                            "passing_yards": player.get("passing_yards", ""),
                            "passing_touchdowns": player.get("passing_touchdowns", ""),
                            "rushing_yards": player.get("rushing_yards", ""),
                            "rushing_touchdowns": player.get("rushing_touchdowns", ""),
                            "interceptions": player.get("interceptions", ""),
                            "fumbles": player.get("fumbles", "")
                        }
                    elif position in ["RB", "WR", "TE"]:
                        player_summary["projections"] = {
                            "rushing_yards": player.get("rushing_yards", ""),
                            "rushing_touchdowns": player.get("rushing_touchdowns", ""),
                            "receiving_yards": player.get("receiving_yards", ""),
                            "receiving_touchdowns": player.get("receiving_touchdowns", ""),
                            "receptions": player.get("receptions", ""),
                            "fumbles": player.get("fumbles", "")
                        }
                    elif position == "K":
                        player_summary["projections"] = {
                            "field_goals": player.get("field_goals", ""),
                            "extra_points": player.get("extra_points", ""),
                            "field_goal_attempts": player.get("field_goal_attempts", "")
                        }
                    elif position == "DEF":
                        player_summary["projections"] = {
                            "sacks": player.get("sacks", ""),
                            "interceptions": player.get("interceptions", ""),
                            "fumble_recoveries": player.get("fumble_recoveries", ""),
                            "defensive_touchdowns": player.get("defensive_touchdowns", "")
                        }
                            
                    all_summarized.append(player_summary)
            
            print(f"DEBUG: Draft Projections {position} chunked processing complete - {len(all_summarized)} players processed from {total_players} total")
            return all_summarized
            
        except Exception as e:
            print(f"ERROR: Draft Projections {position} chunked processing failed: {e}")
            # Fallback to processing first 30 players if chunked processing fails
            return self._process_draft_projections_fallback(players_list[:30], position)
    
    def _process_draft_projections_fallback(self, players_list: List[Dict[str, Any]], position: str) -> List[Dict[str, Any]]:
        """Fallback processing for draft projections data"""
        fallback_summary = []
        for rank, player in enumerate(players_list, 1):
            if isinstance(player, dict):
                player_summary = {
                    "rank": rank,
                    "name": player.get("name", ""),
                    "team": player.get("team", ""),
                    "position": player.get("position", position),
                    "player_id": player.get("playerId", "")
                }
                fallback_summary.append(player_summary)
        return fallback_summary

    def _extract_player_names_from_query(self, query: str) -> List[str]:
        """
        Extract potential player names from the query text.
        This looks for capitalized words that could be player names.
        """
        import re
        
        # Convert query to lowercase for processing
        query_lower = query.lower()
        
        # Look for common name patterns
        # This is a simple implementation - could be enhanced with a player database
        potential_names = []
        
        # Look for specific patterns like "firstname lastname" 
        # Split by common separators and look for capitalized words
        words = re.findall(r'\b[A-Z][a-z]+\b', query)
        
        # Group consecutive capitalized words as potential names
        i = 0
        while i < len(words):
            if i + 1 < len(words):
                # Check if two consecutive words could be a name
                potential_name = f"{words[i]} {words[i+1]}"
                potential_names.append(potential_name)
                i += 2
            else:
                i += 1
        
        # Also check for single names like "Gordon", "Mahomes" etc.
        single_names = re.findall(r'\b[A-Z][a-z]{3,}\b', query)
        potential_names.extend(single_names)
        
        # Remove duplicates and common words
        common_words = {'NFL', 'ROS', 'VORP', 'Fantasy', 'Football', 'Player', 'Team', 'Season', 'Week', 'Analysis', 'Projections'}
        filtered_names = []
        for name in potential_names:
            if name not in common_words and len(name) > 2:
                filtered_names.append(name)
        
        return list(set(filtered_names))  # Remove duplicates

    def _prioritize_mentioned_players_in_ros(self, ros_data: Dict[str, Any], mentioned_players: List[str]) -> Dict[str, Any]:
        """
        Prioritize mentioned players in ROS data to ensure they appear in truncated context.
        
        Args:
            ros_data: The ROS projections data
            mentioned_players: List of player names mentioned in the query
            
        Returns:
            Modified ROS data with mentioned players prioritized
        """
        if not mentioned_players or not isinstance(ros_data, dict):
            return ros_data
        
        print(f"DEBUG: Prioritizing players {mentioned_players} in ROS data")
        
        modified_ros = ros_data.copy()
        
        # For each position, prioritize mentioned players
        for position, players in ros_data.items():
            if not isinstance(players, list) or position in ["season", "metadata"]:
                continue
                
            prioritized_players = []
            remaining_players = []
            
            # First pass: find mentioned players
            for player in players:
                if not isinstance(player, dict):
                    continue
                    
                player_name = player.get("name", "").lower()
                is_mentioned = False
                
                for mentioned_player in mentioned_players:
                    # Check if any part of the mentioned name matches the player name
                    mentioned_parts = mentioned_player.lower().split()
                    if any(part in player_name for part in mentioned_parts if len(part) > 2):
                        print(f"DEBUG: Found mentioned player {mentioned_player} -> {player.get('name', '')} in {position}")
                        prioritized_players.append(player)
                        is_mentioned = True
                        break
                        
                if not is_mentioned:
                    remaining_players.append(player)
            
            # Combine: mentioned players first, then top performers
            max_players_per_position = 15  # Limit to control context size
            combined_players = prioritized_players + remaining_players[:max_players_per_position - len(prioritized_players)]
            
            if len(combined_players) != len(players):
                print(f"DEBUG: {position} players reduced from {len(players)} to {len(combined_players)} (prioritized: {len(prioritized_players)})")
            
            modified_ros[position] = combined_players
        
        return modified_ros

    def _prioritize_mentioned_players_in_draft_projections(self, draft_data: Dict[str, Any], mentioned_players: List[str]) -> Dict[str, Any]:
        """
        Prioritize mentioned players in draft projections data to ensure they appear in truncated context.
        This works on the SUMMARIZED data structure (after _summarize_draft_projections processing).
        
        Args:
            draft_data: The summarized draft projections data (with "positions" key containing processed data)
            mentioned_players: List of player names mentioned in the query
            
        Returns:
            Modified draft projections data with mentioned players prioritized
        """
        if not mentioned_players or not isinstance(draft_data, dict):
            return draft_data
        
        print(f"DEBUG: Prioritizing players {mentioned_players} in draft projections data")
        
        modified_draft = draft_data.copy()
        
        # Handle the summarized structure: {season: 2025, positions: {QB: {count: X, all_players: [...]}, ...}}
        if "positions" in draft_data:
            modified_positions = {}
            
            for position, position_data in draft_data["positions"].items():
                if not isinstance(position_data, dict) or "all_players" not in position_data:
                    modified_positions[position] = position_data
                    continue
                    
                players = position_data["all_players"]
                if not isinstance(players, list):
                    modified_positions[position] = position_data
                    continue
                
                # Debug: Log the first few players in K position to see if Lenny Krieg is there
                if position == "K":
                    print(f"DEBUG: K position has {len(players)} players")
                    for i, player in enumerate(players[:10]):  # Show first 10 players
                        player_name = player.get('name', 'NO_NAME') if isinstance(player, dict) else str(player)
                        print(f"DEBUG: K player {i+1}: {player_name} ({type(player)})")
                    # Check if Lenny Krieg is in the full list
                    krieg_found = any("krieg" in str(player.get('name', '')).lower() for player in players if isinstance(player, dict))
                    print(f"DEBUG: Lenny Krieg found in K position: {krieg_found}")
                    
                prioritized_players = []
                remaining_players = []
                
                # First pass: find mentioned players
                for player in players:
                    if not isinstance(player, dict):
                        continue
                        
                    player_name = player.get("name", "").lower()
                    is_mentioned = False
                    
                    # Debug: Check if this is Lenny Krieg specifically
                    if "krieg" in player_name or "lenny" in player_name:
                        print(f"DEBUG: Examining potential Lenny Krieg match: '{player.get('name', '')}' in {position}")
                    
                    for mentioned_player in mentioned_players:
                        # Check if any part of the mentioned name matches the player name
                        mentioned_parts = mentioned_player.lower().split()
                        
                        # Debug for Lenny Krieg specifically
                        if "krieg" in mentioned_player.lower() or "lenny" in mentioned_player.lower():
                            print(f"DEBUG: Checking '{mentioned_player}' parts {mentioned_parts} against '{player_name}'")
                        
                        if any(part in player_name for part in mentioned_parts if len(part) > 2):
                            print(f"DEBUG: Found mentioned player {mentioned_player} -> {player.get('name', '')} in draft projections {position}")
                            prioritized_players.append(player)
                            is_mentioned = True
                            break
                            
                    if not is_mentioned:
                        remaining_players.append(player)
                
                # Combine: mentioned players first, then top performers
                # For small positions like K, include all players when mentioned players are found
                if position == "K" and prioritized_players:
                    max_players_per_position = len(players)  # Include all kickers if mentioned player found
                else:
                    max_players_per_position = 30 if prioritized_players else 20  # Increase limit when mentioned players found
                combined_players = prioritized_players + remaining_players[:max_players_per_position - len(prioritized_players)]
                
                if len(combined_players) != len(players):
                    print(f"DEBUG: Draft projections {position} players reduced from {len(players)} to {len(combined_players)} (prioritized: {len(prioritized_players)})")
                
                # Update the position data with prioritized players
                modified_position_data = position_data.copy()
                modified_position_data["all_players"] = combined_players
                modified_positions[position] = modified_position_data
                
            modified_draft["positions"] = modified_positions
            
        return modified_draft

    def _prioritize_mentioned_players_in_fantasy_rankings(self, rankings_data: Union[List[Dict[str, Any]], Dict[str, Any]], mentioned_players: List[str], endpoint_type: str) -> Union[List[Dict[str, Any]], Dict[str, Any]]:
        """
        Prioritize mentioned players in any fantasy rankings data to ensure they appear in truncated context.
        Works with various Fantasy Nerds API response formats.
        
        Args:
            rankings_data: The fantasy rankings data (list or dict format)
            mentioned_players: List of player names mentioned in the query
            endpoint_type: Type of endpoint (e.g., "draft_rankings", "weekly_rankings", "dynasty", etc.)
            
        Returns:
            Modified rankings data with mentioned players prioritized
        """
        if not mentioned_players or not rankings_data:
            return rankings_data
        
        print(f"DEBUG: Prioritizing players {mentioned_players} in {endpoint_type} data")
        
        # Handle list format (direct player list)
        if isinstance(rankings_data, list):
            return self._prioritize_players_in_list(rankings_data, mentioned_players, endpoint_type)
        
        # Handle dictionary format
        elif isinstance(rankings_data, dict):
            modified_rankings = rankings_data.copy()
            
            # Case 1: Position-keyed dictionary (e.g., {"QB": [...], "RB": [...], ...})
            if any(pos in rankings_data for pos in ["QB", "RB", "WR", "TE", "K", "DEF"]):
                print(f"DEBUG: Processing position-keyed {endpoint_type} data")
                
                for position, players in rankings_data.items():
                    if not isinstance(players, list) or position in ["season", "metadata"]:
                        continue
                        
                    modified_rankings[position] = self._prioritize_players_in_list(players, mentioned_players, f"{endpoint_type}_{position}")
            
            # Case 2: Players in a "players" or "players_sample" key
            elif "players" in rankings_data and isinstance(rankings_data["players"], list):
                print(f"DEBUG: Processing players key in {endpoint_type} data")
                modified_rankings["players"] = self._prioritize_players_in_list(rankings_data["players"], mentioned_players, endpoint_type)
                
            elif "players_sample" in rankings_data and isinstance(rankings_data["players_sample"], list):
                print(f"DEBUG: Processing players_sample key in {endpoint_type} data")
                modified_rankings["players_sample"] = self._prioritize_players_in_list(rankings_data["players_sample"], mentioned_players, endpoint_type)
            
            # Case 3: Data in a "data" key
            elif "data" in rankings_data:
                print(f"DEBUG: Processing data key in {endpoint_type} data")
                modified_rankings["data"] = self._prioritize_mentioned_players_in_fantasy_rankings(rankings_data["data"], mentioned_players, endpoint_type)
            
            return modified_rankings
        
        return rankings_data

    def _prioritize_players_in_list(self, players_list: List[Dict[str, Any]], mentioned_players: List[str], context: str) -> List[Dict[str, Any]]:
        """
        Helper function to prioritize mentioned players in a list of player dictionaries.
        
        Args:
            players_list: List of player dictionaries
            mentioned_players: List of player names mentioned in the query
            context: Context string for debugging
            
        Returns:
            Reordered list with mentioned players first
        """
        if not players_list or not mentioned_players:
            return players_list
            
        prioritized_players = []
        remaining_players = []
        
        # First pass: find mentioned players
        for player in players_list:
            if not isinstance(player, dict):
                remaining_players.append(player)
                continue
                
            player_name = player.get("name", player.get("display_name", "")).lower()
            is_mentioned = False
            
            for mentioned_player in mentioned_players:
                # Check if any part of the mentioned name matches the player name
                mentioned_parts = mentioned_player.lower().split()
                if any(part in player_name for part in mentioned_parts if len(part) > 2):
                    print(f"DEBUG: Found mentioned player {mentioned_player} -> {player.get('name', player.get('display_name', ''))} in {context}")
                    prioritized_players.append(player)
                    is_mentioned = True
                    break
                    
            if not is_mentioned:
                remaining_players.append(player)
        
        # Combine: mentioned players first, then remaining players
        max_players = 30  # Reasonable limit for context size
        combined_players = prioritized_players + remaining_players[:max_players - len(prioritized_players)]
        
        if len(combined_players) != len(players_list):
            print(f"DEBUG: {context} players reduced from {len(players_list)} to {len(combined_players)} (prioritized: {len(prioritized_players)})")
        
        return combined_players

    def _prioritize_mentioned_teams_in_standings(self, standings_data: Dict[str, Any], mentioned_teams: List[str]) -> Dict[str, Any]:
        """
        Prioritize mentioned teams in standings data to ensure they appear in truncated context.
        
        Args:
            standings_data: The standings data
            mentioned_teams: List of team names mentioned in the query
            
        Returns:
            Modified standings data with mentioned teams prioritized
        """
        if not mentioned_teams or not isinstance(standings_data, dict):
            return standings_data
        
        print(f"DEBUG: Prioritizing teams {mentioned_teams} in standings data")
        
        modified_standings = standings_data.copy()
        
        if "conferences" in standings_data:
            modified_conferences = []
            
            for conference in standings_data["conferences"]:
                modified_conference = conference.copy()
                modified_divisions = []
                
                for division in conference.get("divisions", []):
                    modified_division = division.copy()
                    teams = division.get("teams", [])
                    
                    # Prioritize mentioned teams within each division
                    prioritized_teams = []
                    remaining_teams = []
                    
                    for team in teams:
                        team_name = team.get("name", "").lower()
                        team_alias = team.get("alias", "").lower()
                        is_mentioned = False
                        
                        for mentioned_team in mentioned_teams:
                            mentioned_lower = mentioned_team.lower()
                            if (mentioned_lower in team_name or mentioned_lower in team_alias or 
                                team_name in mentioned_lower or team_alias in mentioned_lower):
                                print(f"DEBUG: Found mentioned team {mentioned_team} -> {team.get('name', '')} in standings")
                                prioritized_teams.append(team)
                                is_mentioned = True
                                break
                                
                        if not is_mentioned:
                            remaining_teams.append(team)
                    
                    # Combine: mentioned teams first, then remaining teams
                    combined_teams = prioritized_teams + remaining_teams
                    modified_division["teams"] = combined_teams
                    modified_divisions.append(modified_division)
                
                modified_conference["divisions"] = modified_divisions
                modified_conferences.append(modified_conference)
            
            modified_standings["conferences"] = modified_conferences
        
        return modified_standings

    def _extract_team_names_from_query(self, query: str) -> List[str]:
        """
        Extract potential team names from the query text.
        This looks for NFL team names and common abbreviations.
        """
        # Common NFL team names and abbreviations
        nfl_teams = {
            'bills', 'dolphins', 'patriots', 'jets', 'ravens', 'bengals', 'browns', 'steelers',
            'texans', 'colts', 'jaguars', 'titans', 'broncos', 'chiefs', 'raiders', 'chargers',
            'cowboys', 'giants', 'eagles', 'commanders', 'bears', 'lions', 'packers', 'vikings',
            'falcons', 'panthers', 'saints', 'buccaneers', 'cardinals', 'rams', '49ers', 'seahawks',
            'buf', 'mia', 'ne', 'nyj', 'bal', 'cin', 'cle', 'pit', 'hou', 'ind', 'jax', 'ten',
            'den', 'kc', 'lv', 'lac', 'dal', 'nyg', 'phi', 'was', 'chi', 'det', 'gb', 'min',
            'atl', 'car', 'no', 'tb', 'ari', 'lar', 'sf', 'sea'
        }
        
        query_lower = query.lower()
        mentioned_teams = []
        
        for team in nfl_teams:
            if team in query_lower.split():  # Exact word match
                mentioned_teams.append(team)
        
        return mentioned_teams

    def _summarize_player_details(self, player_details_data: Union[Dict[str, Any], List[Dict[str, Any]]]) -> Dict[str, Any]:
        """
        Summarize detailed player information from the NFL players endpoint.
        This handles the specific format returned by get_player_detailed_info.
        """
        try:
            if isinstance(player_details_data, dict):
                # Check if it's an error response
                if "error" in player_details_data:
                    return {
                        "error": player_details_data["error"],
                        "player_found": False
                    }
                
                # Check if it contains player_data (expected format)
                if "player_data" in player_details_data:
                    player_data = player_details_data["player_data"]
                    metadata = player_details_data.get("metadata", {})
                    
                    # Summarize the first few players if it's a list
                    if isinstance(player_data, list) and len(player_data) > 0:
                        summarized_players = []
                        for i, player in enumerate(player_data[:5]):  # Limit to first 5 players
                            summarized_player = {
                                "name": player.get("name", "Unknown"),
                                "position": player.get("position", "N/A"),
                                "team": player.get("team", "N/A"),
                                "jersey_number": player.get("jersey", "N/A"),
                                "team": player.get("team", "N/A"),
                                "jersey_number": player.get("jersey", "N/A"),
                                "height": player.get("height", "N/A"),
                                "weight": player.get("weight", "N/A"),
                                "age": player.get("age", "N/A"),
                                "experience": player.get("experience", "N/A"),
                                "college": player.get("college", "N/A"),
                                "status": player.get("status", "N/A")
                            }
                            # Add any additional relevant stats if present
                            if "stats" in player:
                                summarized_player["stats"] = player["stats"]
                            
                            summarized_players.append(summarized_player)
                        
                        return {
                            "player_found": True,
                            "players": summarized_players,
                            "total_players_found": len(player_data),
                            "search_details": metadata
                        }
                    
                    # If single player object
                    elif isinstance(player_data, dict):
                        return {
                            "player_found": True,
                            "player": {
                                "name": player_data.get("name", "Unknown"),
                                "position": player_data.get("position", "N/A"),
                                "team": player_data.get("team", "N/A"),
                                "jersey_number": player_data.get("jersey", "N/A"),
                                "height": player_data.get("height", "N/A"),
                                "weight": player_data.get("weight", "N/A"),
                                "age": player_data.get("age", "N/A"),
                                "experience": player_data.get("experience", "N/A"),
                                "college": player_data.get("college", "N/A"),
                                "status": player_data.get("status", "N/A"),
                                "stats": player_data.get("stats", {})
                            },
                            "search_details": metadata
                        }
                
                # Direct player data format
                return {
                    "player_found": True,
                    "player": {
                        "name": player_details_data.get("name", "Unknown"),
                        "position": player_details_data.get("position", "N/A"),
                        "team": player_details_data.get("team", "N/A"),
                        "jersey_number": player_details_data.get("jersey", "N/A"),
                        "additional_info": "Direct player data format"
                    }
                }
            
            return {"error": "Unexpected player details format", "player_found": False}
            
        except Exception as e:
            print(f"Error summarizing player details: {str(e)}")
            return {"error": f"Failed to summarize player details: {str(e)}", "player_found": False}

llm_service = LLMService()
