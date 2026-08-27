from transitguard.easy import assess_simple_transfer


assessment = assess_simple_transfer(
    requested_start="08:35",
    origin_station="대구역앞",
    transfer_station="중앙로역",
    destination_station="동대구역건너",
    first_route="101",
    second_route="708",
    first_departure="08:40",
    transfer_arrival="08:55",
    second_departure="09:06",
    final_arrival="09:22",
    next_vehicle_arrivals=["09:06", "09:12"],
    walking_minutes=4,
    minimum_buffer_minutes=3,
)

print(assessment.summary)
print("추천:")
for suggestion in assessment.suggestions:
    print("-", suggestion)
print("상세:", assessment.to_dict())
