"""Fictional demo businesses (SPEC §21). Names, phones and addresses are made up.

The assistant eval datasets (evals/datasets/*.yaml) are written against this data, so keep
them in sync when you change prices, tags or FAQs here.
"""

from __future__ import annotations

from typing import Any

DEMO_PASSWORD = "demo-password-123"
ADMIN_EMAIL = "admin@example.com"
ADMIN_PASSWORD = "admin-password-123"

TENANTS: list[dict[str, Any]] = [
    {
        "owner": {"name": "Meera Iyer", "email": "bakery.owner@example.com"},
        "staff": {"name": "Arjun Rao", "email": "bakery.staff@example.com"},
        "tenant": {
            "name": "Demo Bakery",
            "slug": "demo-bakery",
            "description": (
                "A home bakery making celebration cakes, brownies and cookies to order. "
                "Everything is baked fresh the same day. Most cakes can be made eggless."
            ),
            "phone": "+919876500001",
            "email": "bakery.owner@example.com",
            "address": "12, 4th Cross, Koramangala 5th Block, Bengaluru 560095",
            "hours_text": "Tue–Sun, 10am–8pm (closed Mondays)",
            "fulfillment_modes": ["delivery", "pickup"],
            "delivery_areas": ["Koramangala", "HSR Layout", "BTM Layout", "Indiranagar"],
            "min_order_paise": 30000,
            "delivery_fee_paise": 5000,
        },
        "menu": [
            (
                "Cakes",
                [
                    {
                        "name": "Chocolate Truffle Cake (500 g)",
                        "price_paise": 65000,
                        "description": "Dark chocolate sponge layered with ganache.",
                        "tags": ["eggless", "bestseller"],
                    },
                    {
                        "name": "Red Velvet Cake (500 g)",
                        "price_paise": 72000,
                        "description": "Classic red velvet with cream cheese frosting.",
                        "tags": [],
                    },
                    {
                        "name": "Pineapple Fresh Cream Cake (500 g)",
                        "price_paise": 55000,
                        "description": "Light sponge with fresh cream and pineapple.",
                        "tags": ["eggless"],
                    },
                    {
                        "name": "Blueberry Cheesecake (6 inch)",
                        "price_paise": 95000,
                        "description": "Baked New York style cheesecake with blueberry compote.",
                        "tags": [],
                        "is_available": False,
                    },
                ],
            ),
            (
                "Brownies & Bars",
                [
                    {
                        "name": "Walnut Brownie (box of 4)",
                        "price_paise": 32000,
                        "description": "Fudgy brownies with toasted walnuts. Contains nuts.",
                        "tags": ["contains nuts"],
                    },
                    {
                        "name": "Gluten-free Almond Brownie (box of 4)",
                        "price_paise": 38000,
                        "description": "Made with almond flour. Contains nuts.",
                        "tags": ["gluten-free", "contains nuts"],
                    },
                ],
            ),
            (
                "Cookies",
                [
                    {
                        "name": "Choco Chip Cookies (box of 6)",
                        "price_paise": 24000,
                        "description": "Crisp edges, chewy centre.",
                        "tags": ["eggless"],
                    },
                    {
                        "name": "Oatmeal Raisin Cookies (box of 6)",
                        "price_paise": 22000,
                        "description": "Made with jaggery instead of refined sugar.",
                        "tags": ["eggless"],
                    },
                ],
            ),
        ],
        "faq": [
            (
                "Can cakes be made eggless?",
                "Yes. Items tagged eggless are always eggless. Other cakes can be made "
                "eggless on request with one day's notice.",
            ),
            (
                "How much notice do you need for custom cakes?",
                "Please order custom or theme cakes at least 2 days in advance.",
            ),
            (
                "Do you add a message on the cake?",
                "Yes, add the message in the order notes (up to 25 characters), free of charge.",
            ),
            (
                "Is your kitchen nut-free?",
                "No. We use nuts in our kitchen, so we cannot guarantee any item is nut-free.",
            ),
        ],
    },
    {
        "owner": {"name": "Suresh Kulkarni", "email": "tiffin.owner@example.com"},
        "staff": {"name": "Lakshmi N", "email": "tiffin.staff@example.com"},
        "tenant": {
            "name": "Demo Tiffin",
            "slug": "demo-tiffin",
            "description": (
                "Home-style vegetarian lunch and dinner tiffins. Daily meals with dal, sabzi, "
                "rice and phulkas. Jain options available."
            ),
            "phone": "+919876500002",
            "email": "tiffin.owner@example.com",
            "address": "Flat 3B, Lakeview Apartments, HSR Layout Sector 2, Bengaluru 560102",
            "hours_text": "Mon–Sat, lunch 12–2pm and dinner 7–9pm",
            "fulfillment_modes": ["delivery"],
            "delivery_areas": ["HSR Layout", "Bellandur", "Agara"],
            "min_order_paise": 15000,
            "delivery_fee_paise": 0,
        },
        "menu": [
            (
                "Meals",
                [
                    {
                        "name": "Regular Veg Thali",
                        "price_paise": 15000,
                        "description": "Dal, one sabzi, rice, 4 phulkas, salad.",
                        "tags": ["bestseller"],
                    },
                    {
                        "name": "Deluxe Veg Thali",
                        "price_paise": 22000,
                        "description": "Dal, two sabzis, rice, 4 phulkas, curd, sweet.",
                        "tags": [],
                    },
                    {
                        "name": "Jain Thali",
                        "price_paise": 18000,
                        "description": "No onion, garlic or root vegetables.",
                        "tags": ["jain"],
                    },
                ],
            ),
            (
                "Add-ons",
                [
                    {
                        "name": "Extra Phulkas (4)",
                        "price_paise": 4000,
                        "description": None,
                        "tags": [],
                    },
                    {
                        "name": "Curd (200 g)",
                        "price_paise": 3000,
                        "description": "Homemade.",
                        "tags": [],
                    },
                    {
                        "name": "Gulab Jamun (2 pcs)",
                        "price_paise": 5000,
                        "description": None,
                        "tags": [],
                    },
                ],
            ),
        ],
        "faq": [
            (
                "Do you offer a monthly subscription?",
                "Yes, 22 lunches a month for ₹3,000. Message us on WhatsApp to subscribe.",
            ),
            (
                "Is the food spicy?",
                "We cook medium spicy. Mention 'less spicy' in the order notes if needed.",
            ),
            (
                "Do you use onion and garlic?",
                "Regular and Deluxe thalis use onion and garlic. The Jain Thali does not.",
            ),
        ],
    },
]
