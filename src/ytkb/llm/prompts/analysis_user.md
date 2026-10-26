METADATI
Titolo: {{ title }}
Canale: {{ channel }}
Pubblicato: {{ published }}
Durata: {{ duration }}
Trascrizione: lingua "{{ language }}", {{ "generata automaticamente" if is_generated else "scritta dall'autore" }} (fonte: {{ source }})
{% if chapters %}
Capitoli dichiarati dall'autore:
{% for c in chapters %}
- {{ c }}
{% endfor %}
{% endif %}
{% if description %}

Descrizione del video (estratto):
{{ description }}
{% endif %}

TRASCRIZIONE ({{ n_segments }} segmenti, ID da {{ first_id }} a {{ last_id }})
{{ transcript }}
