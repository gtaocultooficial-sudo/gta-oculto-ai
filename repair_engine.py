class RepairEngine:
    """Bounded repair planner. It never performs arbitrary self-modifying code changes."""
    STRATEGIES={
      'ffprobe_failed':['rerender'],
      'not_vertical':['rerender'],
      'low_fps':['rerender'],
      'no_audio':['rerender'],
      'duration_outlier':['rerender'],
      'caption_fragments_or_source_names':['rerender_clean_captions'],
      'internal_metadata_in_narration':['regenerate_script'],
      'short_narration':['regenerate_script'],
      'possible_metadata_date_fragment':['regenerate_script'],
    }
    def plan(self, issues, tried):
        for issue in issues:
            for strategy in self.STRATEGIES.get(issue.split(':')[0],[]):
                if strategy not in tried: return strategy
        if 'rerender' not in tried and issues: return 'rerender'
        return None
