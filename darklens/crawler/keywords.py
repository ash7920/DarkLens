"""
Multilingual keyword lists used by the page classifier, URL prioritiser and
safe-interaction policy.  Covers EN, DE, FR, ES, IT, NL, PL, PT, SV — the
languages of the bulk of EU e-commerce.  Matching is substring-based on
lower-cased URL paths, anchor text and button labels.
"""

PAGE_KEYWORDS = {
    "checkout": [
        "checkout", "check-out", "kasse", "zur-kasse", "commande", "paiement",
        "pago", "finalizar", "tramitar", "cassa", "acquisto", "afrekenen", "bestellen",
        "kassa", "zamowienie", "zamówienie", "finalizar-compra", "order/confirm",
    ],
    "cart": [
        "cart", "basket", "bag", "warenkorb", "panier", "carrito", "cesta",
        "carrello", "winkelwagen", "winkelmand", "koszyk", "carrinho", "varukorg",
        "kundvagn", "/trolley",
    ],
    "subscription": [
        "subscription", "subscriptions", "membership", "abo", "abonnement",
        "suscripcion", "suscripción", "abbonamento", "lidmaatschap", "subskrypcja",
        "cancel", "kuendigen", "kündigen",
        "resilier", "résilier", "annuler", "cancelar", "disdici", "opzeggen",
        "unsubscribe", "manage-plan",
    ],
    "account": [
        "account", "konto", "mein-konto", "compte", "mon-compte", "cuenta",
        "mi-cuenta", "account/login", "profilo", "mijn-account", "login", "signin",
        "sign-in", "register", "anmelden", "connexion", "iniciar-sesion",
    ],
    "product": [
        "/product", "/products/", "/p/", "/dp/", "/item", "/artikel", "/produit",
        "/producto", "/prodotto", "/produkt", "/catalogue/", "/pd/", "/-p-",
        "/sku", "/offer", "/angebot",
    ],
    "category": [
        "/category", "/categories", "/collections", "/c/", "/kategorie",
        "/categorie", "/categoria", "/shop/", "/catalog", "/sale", "/outlet",
        "/deals", "/angebote", "/soldes", "/rebajas", "/saldi", "/aanbiedingen",
        "/men", "/women", "/herren", "/damen", "/homme", "/femme",
    ],
    "info": [
        "about", "privacy", "datenschutz", "impressum", "terms", "agb", "cgv",
        "legal", "imprint", "careers", "jobs", "press", "blog", "help", "faq",
        "contact", "kontakt", "cookie-policy", "sitemap", "store-locator",
        "investor", "newsroom", "magazine",
    ],
}

# Anchor/button text that hints at the page type behind a link.
ANCHOR_HINTS = {
    "checkout": ["checkout", "zur kasse", "commander", "tramitar pedido", "afrekenen", "procedi"],
    "cart": ["cart", "basket", "bag", "warenkorb", "panier", "carrito", "carrello",
             "winkelwagen", "koszyk", "cesta"],
    "subscription": ["subscription", "membership", "cancel", "kündigen", "abo", "abonnement",
                     "unsubscribe", "manage plan", "my plan"],
    "product": ["view product", "details", "shop now", "jetzt kaufen", "voir le produit",
                "ver producto", "bekijk"],
    "deal": ["sale", "deal", "offer", "angebot", "promo", "soldes", "rebajas", "saldi",
             "aanbieding", "black friday", "flash"],
}

# Clicking these could spend money, create obligations or change account
# state irreversibly.  Never clicked.
BLOCKED_ACTIONS = [
    "place order", "buy now", "pay now", "pay ", "payment", "purchase", "confirm order",
    "complete order", "submit order", "order now", "kaufen", "jetzt kaufen", "zahlungspflichtig",
    "bestellung abschicken", "commander et payer", "payer", "valider la commande", "comprar ahora",
    "pagar", "confirmar pedido", "acquista ora", "paga", "conferma ordine", "nu kopen",
    "betalen", "bestelling plaatsen", "kup teraz", "zapłać", "delete", "remove account",
    "close account", "deactivate", "logout", "log out", "sign out", "abmelden",
    "déconnexion", "cerrar sesión", "subscribe", "sign up", "register", "create account",
    "jetzt registrieren", "s'inscrire", "regístrate", "iscriviti", "apply", "submit",
    "send", "absenden", "envoyer", "enviar", "invia", "verzenden", "1-click", "one-click",
    "start free trial", "start trial", "probemonat", "essai gratuit", "prueba gratis",
    "confirm cancellation",
]

# Allowed only when the crawl is configured with allow_add_to_cart=True
# (as in Mathur et al. 2019); reversible and needed to reach cart/checkout.
CONDITIONAL_ACTIONS = [
    "add to cart", "add to basket", "add to bag", "in den warenkorb", "ajouter au panier",
    "añadir al carrito", "añadir a la cesta", "aggiungi al carrello", "in winkelwagen",
    "toevoegen aan winkelwagen", "do koszyka", "adicionar ao carrinho", "lägg i varukorgen",
]

# Safe, information-revealing interactions we actively want to try.
REVEAL_ACTIONS = {
    "cookie_settings": ["cookie settings", "settings", "preferences", "privacy settings", "manage cookies", "manage preferences", "customise",
                        "customize", "einstellungen", "cookie-einstellungen", "paramètres",
                        "personnaliser", "configurar", "preferenze", "personalizza",
                        "instellingen", "more options", "options"],
    "expand": ["details", "more info", "read more", "show more", "view more", "mehr anzeigen",
               "voir plus", "ver más", "mostra di più", "meer weergeven", "specifications",
               "shipping", "delivery", "versand", "livraison", "envío", "spedizione"],
    "close_popup": ["no thanks", "no, thanks", "close", "dismiss", "not now", "maybe later",
                    "nein danke", "non merci", "no gracias", "no grazie", "nee bedankt",
                    "×", "✕"],
    "consent_reject": ["reject all", "decline all", "refuse all", "reject", "decline",
                       "alle ablehnen", "ablehnen", "tout refuser", "refuser", "rechazar todo",
                       "rechazar", "rifiuta tutto", "rifiuta", "alles weigeren", "weigeren",
                       "odrzuć wszystkie", "rejeitar"],
    "variant": ["size", "größe", "taille", "talla", "taglia", "maat", "colour", "color",
                "farbe", "couleur"],
}
