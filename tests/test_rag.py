from app.services.rag import _speed_to_pace, build_context


class TestSpeedToPace:
    def test_normal_speed(self):
        assert _speed_to_pace(2.78) == "5:59/km"

    def test_fast_speed(self):
        assert _speed_to_pace(3.70) == "4:30/km"

    def test_slow_speed(self):
        assert _speed_to_pace(1.67) == "9:58/km"

    def test_zero_returns_na(self):
        assert _speed_to_pace(0) == "N/A"

    def test_negative_returns_na(self):
        assert _speed_to_pace(-1.0) == "N/A"

    def test_none_returns_na(self):
        assert _speed_to_pace(None) == "N/A"


class TestBuildContext:
    def test_empty_list_returns_fixed_message(self):
        result = build_context([])
        assert result == "没有找到相关的跑步记录。"

    def test_single_activity(self):
        activities = [
            {
                "start_date": "2026-03-15T08:00:00",
                "name": "晨跑",
                "distance_km": 5.02,
                "pace": "5:30/km",
                "similarity": 0.87,
                "description": "2026年03月15日 晨跑",
            }
        ]
        result = build_context(activities)
        assert "晨跑" in result
        assert "5.02km" in result
        assert "5:30/km" in result
        assert "0.87" in result
        assert "2026-03-15" in result

    def test_multiple_activities_numbered(self):
        activities = [
            {
                "start_date": "2026-03-15T08:00:00",
                "name": "跑步A",
                "distance_km": 5.0,
                "pace": "5:30/km",
                "similarity": 0.9,
                "description": "描述A",
            },
            {
                "start_date": "2026-03-16T08:00:00",
                "name": "跑步B",
                "distance_km": 10.0,
                "pace": "6:00/km",
                "similarity": 0.8,
                "description": "描述B",
            },
        ]
        result = build_context(activities)
        assert "【最近一次】" in result
        assert "2." in result
        assert "跑步A" in result
        assert "跑步B" in result
