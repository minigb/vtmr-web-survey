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

def extract_video_info(file_path):
    """Extract condition and video ID from file path."""
    # file_path format: "videos/0/mixed_1.mp4"
    parts = file_path.split('/')
    if len(parts) >= 3:
        condition = parts[1]  # "0", "1", "2", etc.
        video_file = parts[2]  # "mixed_1.mp4"
        video_id = os.path.splitext(video_file)[0]  # "mixed_1"
        return condition, video_id, f"{condition}_{video_id}"
    return "unknown", "unknown", file_path

def analyze_results(results_data):
    """Analyze survey results and calculate winning rates."""
    
    # Statistics storage
    video_stats = defaultdict(lambda: {
        'wins': 0,
        'losses': 0,
        'total_appearances': 0,
        'participants': set(),
        'win_rate': 0.0,
        'condition': '',
        'video_id': '',
        'full_path': ''
    })
    
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
            
        # Skip obviously invalid entries (like injection attempts)
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
            if not isinstance(vote, dict) or 'winner' not in vote or 'loser' not in vote:
                continue
                
            total_comparisons += 1
            
            # Process winner
            winner = vote['winner']
            if 'file' in winner:
                condition, video_id, full_id = extract_video_info(winner['file'])
                video_stats[full_id]['wins'] += 1
                video_stats[full_id]['total_appearances'] += 1
                video_stats[full_id]['participants'].add(participant_id)
                video_stats[full_id]['condition'] = condition
                video_stats[full_id]['video_id'] = video_id
                video_stats[full_id]['full_path'] = winner['file']
            
            # Process loser
            loser = vote['loser']
            if 'file' in loser:
                condition, video_id, full_id = extract_video_info(loser['file'])
                video_stats[full_id]['losses'] += 1
                video_stats[full_id]['total_appearances'] += 1
                video_stats[full_id]['participants'].add(participant_id)
                video_stats[full_id]['condition'] = condition
                video_stats[full_id]['video_id'] = video_id
                video_stats[full_id]['full_path'] = loser['file']
    
    # Calculate win rates
    for video_id, stats in video_stats.items():
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
    print(f"🎬 Total unique videos: {len(video_stats)}")
    print()
    
    # Participant details
    print("👥 PARTICIPANT DETAILS:")
    print("-" * 30)
    for participant_id in valid_participants:
        stats = participant_stats[participant_id]
        print(f"  {participant_id}: {stats['total_votes']} votes ({stats['timestamp'][:10]})")
    print()
    
    # Sort videos by win rate
    sorted_videos = sorted(video_stats.items(), key=lambda x: x[1]['win_rate'], reverse=True)
    
    print("🏆 VIDEO WINNING RATES (Ranked):")
    print("-" * 80)
    print(f"{'Rank':<4} {'Video ID':<15} {'Condition':<9} {'Win Rate':<9} {'Wins':<5} {'Total':<5} {'Participants':<12}")
    print("-" * 80)
    
    for rank, (video_id, stats) in enumerate(sorted_videos, 1):
        print(f"{rank:<4} {stats['video_id']:<15} {stats['condition']:<9} "
              f"{stats['win_rate']:<8.1f}% {stats['wins']:<5} {stats['total_appearances']:<5} {stats['participants']:<12}")
    
    print()
    
    # Condition analysis
    print("📈 ANALYSIS BY CONDITION:")
    print("-" * 40)
    condition_stats = defaultdict(lambda: {'videos': [], 'total_wins': 0, 'total_appearances': 0})
    
    for video_id, stats in video_stats.items():
        condition = stats['condition']
        condition_stats[condition]['videos'].append(stats)
        condition_stats[condition]['total_wins'] += stats['wins']
        condition_stats[condition]['total_appearances'] += stats['total_appearances']
    
    for condition in sorted(condition_stats.keys()):
        stats = condition_stats[condition]
        avg_win_rate = (stats['total_wins'] / stats['total_appearances'] * 100) if stats['total_appearances'] > 0 else 0
        print(f"  Condition {condition}: {len(stats['videos'])} videos, {avg_win_rate:.1f}% average win rate")
        
        # Show individual videos in this condition
        for video_stats_item in sorted(stats['videos'], key=lambda x: x['win_rate'], reverse=True):
            print(f"    └─ {video_stats_item['video_id']}: {video_stats_item['win_rate']:.1f}% ({video_stats_item['wins']}/{video_stats_item['total_appearances']})")

def export_to_csv(video_stats, output_file='data/analysis_results.csv'):
    """Export results to CSV file."""
    print(f"\n📄 Exporting results to {output_file}...")
    
    # Ensure data directory exists
    os.makedirs(os.path.dirname(output_file), exist_ok=True)
    
    with open(output_file, 'w', newline='') as csvfile:
        fieldnames = ['video_id', 'condition', 'full_path', 'wins', 'losses', 'total_appearances', 
                     'win_rate', 'participants_count']
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        
        writer.writeheader()
        
        # Sort by win rate descending
        sorted_videos = sorted(video_stats.items(), key=lambda x: x[1]['win_rate'], reverse=True)
        
        for video_id, stats in sorted_videos:
            writer.writerow({
                'video_id': stats['video_id'],
                'condition': stats['condition'],
                'full_path': stats['full_path'],
                'wins': stats['wins'],
                'losses': stats['losses'],
                'total_appearances': stats['total_appearances'],
                'win_rate': round(stats['win_rate'], 2),
                'participants_count': stats['participants']
            })
    
    print(f"✅ Results exported to {output_file}")

def create_visualization_data(video_stats):
    """Create data suitable for visualization (can be extended with matplotlib/plotly)."""
    sorted_videos = sorted(video_stats.items(), key=lambda x: x[1]['win_rate'], reverse=True)
    
    visualization_data = {
        'video_names': [stats['video_id'] for _, stats in sorted_videos],
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
