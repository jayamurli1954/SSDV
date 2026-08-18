from __future__ import annotations

# GST state code -> (name, cities)
STATES: dict[str, tuple[str, tuple[str, ...]]] = {
    "27": (
        "Maharashtra",
        (
            "Pune",
            "Mumbai",
            "Thane",
            "Nashik",
            "Nagpur",
            "Aurangabad",
            "Kolhapur",
            "Navi Mumbai",
            "Solapur",
            "Satara",
            "Ahmednagar",
            "Sangli",
        ),
    ),
    "24": ("Gujarat", ("Ahmedabad", "Vadodara", "Surat", "Rajkot", "Bhavnagar")),
    "29": ("Karnataka", ("Bengaluru", "Mysuru", "Hubballi", "Belagavi", "Mangaluru")),
    "23": ("Madhya Pradesh", ("Indore", "Bhopal", "Jabalpur", "Gwalior")),
    "36": ("Telangana", ("Hyderabad", "Warangal", "Nizamabad")),
    "07": ("Delhi", ("New Delhi", "Dwarka", "Okhla", "Narela")),
    "08": ("Rajasthan", ("Jaipur", "Jodhpur", "Kota", "Udaipur")),
    "33": ("Tamil Nadu", ("Chennai", "Coimbatore", "Madurai", "Salem")),
    "09": ("Uttar Pradesh", ("Lucknow", "Noida", "Kanpur", "Ghaziabad")),
    "06": ("Haryana", ("Gurugram", "Faridabad", "Panipat")),
    "03": ("Punjab", ("Ludhiana", "Amritsar", "Jalandhar")),
    "32": ("Kerala", ("Ernakulam", "Thiruvananthapuram", "Kozhikode")),
    "19": ("West Bengal", ("Kolkata", "Howrah", "Durgapur")),
    "37": ("Andhra Pradesh", ("Visakhapatnam", "Vijayawada", "Guntur")),
}

HOME_STATE = "27"
OTHER_STATES = tuple(code for code in STATES if code != HOME_STATE)


def state_name(code: str) -> str:
    return STATES[code][0]


def cities(code: str) -> tuple[str, ...]:
    return STATES[code][1]
