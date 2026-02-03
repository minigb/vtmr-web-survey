#!/usr/bin/env python3
"""
VTMR Survey Results Analysis Tool

This script analyzes the winning rates for each video sample from the survey results.
It provides detailed statistics, visualizations, and exports results to CSV.
"""

import json
import os
import sys
from collections import defaultdict, Counter
from datetime import datetime
import csv

def load_results(file_path='data/results.json'):
    """Load survey results from JSON file."""
    try:
        with open(file_path, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"❌ Results file not found: {file_path}")
        return {}
    except json.JSONDecodeError:
        print(f"❌ Invalid JSON in results file: {file_path}")
        return {}

def extract_video_info(video_obj):
    """Extract condition and video ID from video object or file path."""
    # Handle both old format (file path) and new format (video object with id)
    if isinstance(video_obj, dict):
        if 'id' in video_obj:
            # New format: ID already includes parent directory (e.g., "0_mixed_1")
            video_id = video_obj['id']
            if '_' in video_id:
                parts = video_id.split('_', 1)  # Split only on first underscore
                condition = parts[0]  # "0"
                base_video_id = parts[1]  # "mixed_1"
                full_video_id = video_id  # "0_mixed_1"
                return condition, base_video_id, full_video_id
            else:
                # Fallback if no underscore
                return "unknown", video_id, video_id
        elif 'file' in video_obj:
            # Fallback to file path analysis
            file_path = video_obj['file']
        else:
            return "unknown", "unknown", "unknown"
    else:
        # Old format: direct file path
        file_path = str(video_obj)
    
    # Analyze file path (fallback method)
    parts = file_path.split('/')
    if len(parts) >= 3:
        condition = parts[1]  # "0", "1", "2", etc.
        video_file = parts[2]  # "mixed_1.mp4"
        base_video_id = os.path.splitext(video_file)[0]  # "mixed_1"
        full_video_id = f"{condition}_{base_video_id}"  # "0_mixed_1"
        return condition, base_video_id, full_video_id
    return "unknown", "unknown", str(video_obj)

def analyze_results(results_data):
    """Analyze survey results and calculate winning rates for multiple metrics."""
    
    # Initialize metrics
    metrics = ['global', 'temporal', 'quality']
    
    # Statistics storage: structured by metric -> video_id -> stats
    video_stats = {
        metric: defaultdict(lambda: {
            'wins': 0,
            'losses': 0,
            'total_appearances': 0,
            'participants': set(),
            'win_rate': 0.0,
            'condition': '',
            'base_video_id': '',
            'full_path': ''
        }) for metric in metrics
    }
    
    participant_stats = {}
    total_comparisons = 0
    valid_participants = []
    
    print("📊 Analyzing survey results...")
    print("=" * 60)
    
    # Process each participant's responses
    for participant_id, votes in results_data.items():
        # Skip empty results or test entries
        if not votes or not isinstance(votes, list):
            continue
            
        # Skip obviously invalid entries
        if len(participant_id) > 50 or any(char in participant_id for char in ['<', '>', '"', '\'', ';']):
            continue
            
        valid_participants.append(participant_id)
        participant_stats[participant_id] = {
            'total_votes': len(votes),
            'timestamp': votes[0].get('ts', 'unknown') if votes else 'unknown'
        }
        
        print(f"👤 {participant_id}: {len(votes)} comparisons")
        
        # Process each vote/comparison
        for vote in votes:
            if not isinstance(vote, dict) or 'results' not in vote:
                continue
                
            total_comparisons += 1
            
            # Process results for each metric
            for metric in metrics:
                if metric not in vote['results']:
                    continue
                    
                result = vote['results'][metric]
                if 'winner' not in result or 'loser' not in result:
                    continue
                
                # Process winner
                winner = result['winner']
                condition, base_video_id, full_video_id = extract_video_info(winner)
                stats = video_stats[metric][full_video_id]
                
                stats['wins'] += 1
                stats['total_appearances'] += 1
                stats['participants'].add(participant_id)
                stats['condition'] = condition
                stats['base_video_id'] = base_video_id
                
                if isinstance(winner, dict) and 'file' in winner:
                    stats['full_path'] = winner['file']
                
                # Process loser
                loser = result['loser']
                condition, base_video_id, full_video_id = extract_video_info(loser)
                stats = video_stats[metric][full_video_id]
                
                stats['losses'] += 1
                stats['total_appearances'] += 1
                stats['participants'].add(participant_id)
                stats['condition'] = condition
                stats['base_video_id'] = base_video_id
                
                if isinstance(loser, dict) and 'file' in loser:
                    stats['full_path'] = loser['file']
    
    # Calculate win rates for all metrics
    for metric in metrics:
        for video_id, stats in video_stats[metric].items():
            if stats['total_appearances'] > 0:
                stats['win_rate'] = (stats['wins'] / stats['total_appearances']) * 100
                stats['participants'] = len(stats['participants'])
    
    return video_stats, participant_stats, total_comparisons, valid_participants

def print_summary_report(video_stats, participant_stats, total_comparisons, valid_participants):
    """Print a comprehensive summary report."""
    
    print(f"\n🎯 SURVEY RESULTS SUMMARY")
    print("=" * 60)
    print(f"📊 Total valid participants: {len(valid_participants)}")
    print(f"🔄 Total comparisons: {total_comparisons}")
    
    # Get total unique videos from the first metric
    first_metric = list(video_stats.keys())[0]
    print(f"🎬 Total unique videos: {len(video_stats[first_metric])}")
    print()
    
    # Participant details
    print("👥 PARTICIPANT DETAILS:")
    print("-" * 30)
    for participant_id in valid_participants:
        stats = participant_stats[participant_id]
        print(f"  {participant_id}: {stats['total_votes']} votes ({stats['timestamp'][:10]})")
    print()
    
    # Report per metric
    for metric in video_stats:
        print(f"\n🏆 {metric.upper()} WINNING RATES (Ranked):")
        print("-" * 100)
        print(f"{'Rank':<4} {'Video ID':<20} {'Condition':<10} {'Win Rate':<10} {'Wins':<6} {'Total':<6} {'Participants':<12}")
        print("-" * 100)
        
        # Sort videos by win rate
        sorted_videos = sorted(video_stats[metric].items(), key=lambda x: x[1]['win_rate'], reverse=True)
        
        for rank, (full_video_id, stats) in enumerate(sorted_videos, 1):
            print(f"{rank:<4} {full_video_id:<20} {stats['condition']:<10} "
                  f"{stats['win_rate']:<9.1f}% {stats['wins']:<6} {stats['total_appearances']:<6} {stats['participants']:<12}")
    
    print()

def export_to_csv(video_stats, output_file='data/analysis_results.csv'):
    """Export results to CSV file."""
    print(f"\n📄 Exporting results to {output_file}...")
    
    # Ensure data directory exists
    os.makedirs(os.path.dirname(output_file), exist_ok=True)
    
    # Get all video IDs from the first metric to ensure we cover all videos
    # Assuming all videos appear in all metrics
    first_metric = list(video_stats.keys())[0]
    all_video_ids = list(video_stats[first_metric].keys())
    
    with open(output_file, 'w', newline='') as csvfile:
        # Build fieldnames dynamically
        fieldnames = ['video_id', 'condition', 'base_video_id', 'full_path']
        for metric in video_stats:
            fieldnames.extend([
                f'{metric}_wins', 
                f'{metric}_losses', 
                f'{metric}_total', 
                f'{metric}_win_rate'
            ])
        fieldnames.append('participants_count')
            
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        
        # Sort by global win rate descending (if available) or just video_id
        sort_metric = 'global' if 'global' in video_stats else first_metric
        
        # Create a list of video data for sorting
        video_rows = []
        for vid in all_video_ids:
            # Base info from the first metric
            base_stats = video_stats[first_metric][vid]
            row = {
                'video_id': vid,
                'condition': base_stats['condition'],
                'base_video_id': base_stats['base_video_id'],
                'full_path': base_stats['full_path'],
                'participants_count': base_stats['participants']
            }
            
            # Add stats for each metric
            for metric in video_stats:
                m_stats = video_stats[metric].get(vid, {
                    'wins': 0, 'losses': 0, 'total_appearances': 0, 'win_rate': 0.0
                })
                row[f'{metric}_wins'] = m_stats['wins']
                row[f'{metric}_losses'] = m_stats['losses']
                row[f'{metric}_total'] = m_stats['total_appearances']
                row[f'{metric}_win_rate'] = round(m_stats['win_rate'], 2)
            
            video_rows.append(row)
            
        # Sort rows by win rate of the sort_metric
        video_rows.sort(key=lambda x: x[f'{sort_metric}_win_rate'], reverse=True)
        
        # Write rows
        for row in video_rows:
            writer.writerow(row)
    
    print(f"✅ Results exported to {output_file}")

def create_visualization_data(video_stats):
    """Create data suitable for visualization (can be extended with matplotlib/plotly)."""
    sorted_videos = sorted(video_stats.items(), key=lambda x: x[1]['win_rate'], reverse=True)
    
    visualization_data = {
        'video_names': [full_video_id for full_video_id, _ in sorted_videos],
        'win_rates': [stats['win_rate'] for _, stats in sorted_videos],
        'conditions': [stats['condition'] for _, stats in sorted_videos],
        'total_appearances': [stats['total_appearances'] for _, stats in sorted_videos]
    }
    
    return visualization_data

def main():
    """Main analysis function."""
    print("🎬 VTMR Survey Results Analysis")
    print("=" * 60)
    
    # Load results
    results_data = load_results()
    
    if not results_data:
        print("❌ No valid results data found.")
        return
    
    # Analyze results
    video_stats, participant_stats, total_comparisons, valid_participants = analyze_results(results_data)
    
    if not video_stats:
        print("❌ No valid video statistics found.")
        return
    
    # Print summary report
    print_summary_report(video_stats, participant_stats, total_comparisons, valid_participants)
    
    # Export to CSV
    export_to_csv(video_stats)
    
    # Create visualization data (for future use)
    viz_data = create_visualization_data(video_stats)
    
    print(f"\n🎉 Analysis complete!")
    print(f"📊 {len(video_stats)} videos analyzed from {len(valid_participants)} participants")
    print(f"📈 Check 'data/analysis_results.csv' for detailed data")

if __name__ == "__main__":
    main()
