# Copyright (c) Microsoft Corporation.
# Licensed under the MIT license.

"""
STAC Query Checker Integration
Adds intelligent query analysis and clarification to the semantic translator
"""
from typing import Dict, List, Any, Optional, Tuple
import logging

class STACQueryChecker:
    """Intelligent STAC query validation and clarification system"""
    
    def __init__(self, semantic_translator):
        self.translator = semantic_translator
        self.logger = logging.getLogger(__name__)
    
    def analyze_query_completeness(self, entities: Dict[str, Any], stac_query: Dict[str, Any], original_query: str) -> Dict[str, Any]:
        """Analyze STAC query completeness and identify missing critical parameters"""
        
        issues = []
        suggestions = []
        severity_score = 0  # 0=perfect, 10=unusable
        
        # Check spatial coverage
        spatial_analysis = self._check_spatial_coverage(entities, stac_query)
        issues.extend(spatial_analysis["issues"])
        suggestions.extend(spatial_analysis["suggestions"])
        severity_score += spatial_analysis["severity"]
        
        # Check temporal coverage
        temporal_analysis = self._check_temporal_coverage(entities, stac_query, original_query)
        issues.extend(temporal_analysis["issues"])
        suggestions.extend(temporal_analysis["suggestions"])
        severity_score += temporal_analysis["severity"]
        
        # Check disaster context
        disaster_analysis = self._check_disaster_context(entities, stac_query)
        issues.extend(disaster_analysis["issues"])
        suggestions.extend(disaster_analysis["suggestions"])
        severity_score += disaster_analysis["severity"]
        
        # Check collection appropriateness
        collection_analysis = self._check_collection_selection(entities, stac_query)
        issues.extend(collection_analysis["issues"])
        suggestions.extend(collection_analysis["suggestions"])
        severity_score += collection_analysis["severity"]
        
        return {
            "overall_quality": self._calculate_quality_score(severity_score),
            "severity_score": severity_score,
            "issues": issues,
            "suggestions": suggestions,
            "needs_clarification": severity_score >= 6,
            "clarification_priority": self._prioritize_clarifications(issues)
        }
    
    def _check_spatial_coverage(self, entities: Dict[str, Any], stac_query: Dict[str, Any]) -> Dict[str, Any]:
        """Check spatial coverage issues"""
        issues = []
        suggestions = []
        severity = 0
        
        bbox = stac_query.get("bbox", [])
        location = entities.get("location", {})
        
        if not bbox or len(bbox) != 4:
            issues.append("No valid location specified - query will search globally")
            suggestions.append("Please specify a location (e.g., 'California', 'Houston, Texas', 'Turkey')")
            severity += 4
        elif not location.get("name"):
            issues.append("Location extracted but confidence is low")
            suggestions.append("Please confirm the specific location you're interested in")
            severity += 2
        else:
            # Check if bbox is too large
            width = abs(bbox[2] - bbox[0])  # longitude span
            height = abs(bbox[3] - bbox[1])  # latitude span
            
            if width > 50 or height > 50:
                issues.append("Area of interest is very large - may return too many results")
                suggestions.append("Consider specifying a smaller region or city")
                severity += 2
        
        return {"issues": issues, "suggestions": suggestions, "severity": severity}
    
    def _check_temporal_coverage(self, entities: Dict[str, Any], stac_query: Dict[str, Any], original_query: str) -> Dict[str, Any]:
        """Check temporal coverage issues"""
        issues = []
        suggestions = []
        severity = 0
        
        datetime_range = stac_query.get("datetime", "")
        temporal = entities.get("temporal", {})
        
        if not datetime_range:
            issues.append("No time period specified - will search all available data")
            suggestions.append("Please specify when you're interested in (e.g., 'September 2023', 'last month', 'after Hurricane Ian')")
            severity += 3
        else:
            # Check for vague relative terms
            relative = temporal.get("relative")
            if relative == "recent" and "recent" in original_query.lower():
                issues.append("'Recent' is ambiguous - could mean days, weeks, or months")
                suggestions.append("Please specify: 'last week', 'last month', 'last 30 days', or a specific date")
                severity += 2
            
            # Check for overly broad time ranges
            if "/" in datetime_range:
                try:
                    from datetime import datetime
                    start_str, end_str = datetime_range.split("/")
                    start_dt = datetime.fromisoformat(start_str.replace('Z', '+00:00'))
                    end_dt = datetime.fromisoformat(end_str.replace('Z', '+00:00'))
                    duration_days = (end_dt - start_dt).days
                    
                    if duration_days > 365:
                        issues.append(f"Time period is very long ({duration_days} days) - may return too many results")
                        suggestions.append("Consider narrowing to a specific season, month, or event timeframe")
                        severity += 1
                except Exception:
                    pass
        
        return {"issues": issues, "suggestions": suggestions, "severity": severity}
    
    def _check_disaster_context(self, entities: Dict[str, Any], stac_query: Dict[str, Any]) -> Dict[str, Any]:
        """Check disaster analysis context"""
        issues = []
        suggestions = []
        severity = 0
        
        disaster = entities.get("disaster", {})
        analysis_intent = entities.get("analysis_intent", {})
        
        disaster_type = disaster.get("type")
        disaster_confidence = disaster.get("confidence", 0)
        
        if disaster_type and disaster_confidence < 0.7:
            issues.append(f"Disaster type '{disaster_type}' detected but with low confidence")
            suggestions.append("Please clarify the specific type of event you're analyzing")
            severity += 1
        elif not disaster_type:
            analysis_type = analysis_intent.get("type", "")
            if "damage" in analysis_type or "impact" in analysis_type:
                issues.append("Damage analysis requested but no specific disaster type identified")
                suggestions.append("What type of event caused the damage? (wildfire, hurricane, flood, earthquake, etc.)")
                severity += 2
        
        return {"issues": issues, "suggestions": suggestions, "severity": severity}
    
    def _check_collection_selection(self, entities: Dict[str, Any], stac_query: Dict[str, Any]) -> Dict[str, Any]:
        """Check satellite collection selection appropriateness"""
        issues = []
        suggestions = []
        severity = 0
        
        collections = stac_query.get("collections", [])
        
        if not collections:
            issues.append("No satellite collections selected - query may not return results")
            suggestions.append("Unable to determine appropriate satellite data - please specify analysis type")
            severity += 4
        elif len(collections) > 8:
            issues.append(f"Too many collections selected ({len(collections)}) - may slow search")
            suggestions.append("Consider being more specific about your analysis needs")
            severity += 1
        
        return {"issues": issues, "suggestions": suggestions, "severity": severity}
    
    def _calculate_quality_score(self, severity_score: int) -> str:
        """Convert severity score to quality rating"""
        if severity_score == 0:
            return "excellent"
        elif severity_score <= 2:
            return "good"
        elif severity_score <= 4:
            return "fair"
        elif severity_score <= 6:
            return "poor"
        else:
            return "unusable"
    
    def _prioritize_clarifications(self, issues: List[str]) -> List[str]:
        """Prioritize which clarifications are most important"""
        priority_order = []
        
        # Location issues first (most critical)
        location_issues = [issue for issue in issues if "location" in issue.lower() or "area" in issue.lower()]
        priority_order.extend(location_issues)
        
        # Time issues second
        time_issues = [issue for issue in issues if "time" in issue.lower() or "recent" in issue.lower()]
        priority_order.extend(time_issues)
        
        # Disaster context third
        disaster_issues = [issue for issue in issues if "disaster" in issue.lower() or "damage" in issue.lower()]
        priority_order.extend(disaster_issues)
        
        # Other issues last
        other_issues = [issue for issue in issues if issue not in priority_order]
        priority_order.extend(other_issues)
        
        return priority_order[:3]  # Top 3 priorities
    
    def generate_clarification_questions(self, analysis: Dict[str, Any], original_query: str) -> List[str]:
        """Generate clarification questions based on analysis"""
        
        if not analysis["needs_clarification"]:
            return []
        
        questions = []
        priority_issues = analysis["clarification_priority"]
        
        # Generate questions based on priority issues
        for issue in priority_issues:
            if "location" in issue.lower():
                questions.append("What specific location are you interested in? (e.g., 'California', 'Houston, Texas', 'Turkey')")
            elif "time" in issue.lower() or "recent" in issue.lower():
                questions.append("What time period should I search? (e.g., 'September 2023', 'last month', 'after Hurricane Ian')")
            elif "disaster" in issue.lower() or "damage" in issue.lower():
                questions.append("What type of event or disaster are you analyzing? (e.g., wildfire, hurricane, earthquake, flooding)")
            elif "collection" in issue.lower():
                questions.append("What type of analysis do you want to perform? (damage assessment, change detection, thermal monitoring)")
        
        # Remove duplicates while preserving order
        seen = set()
        unique_questions = []
        for q in questions:
            if q not in seen:
                seen.add(q)
                unique_questions.append(q)
        
        return unique_questions[:3]  # Limit to 3 questions
