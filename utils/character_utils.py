from typing import Union


# Coûts en points d'expérience (XP) pour les freebies
XP_COST_FREEBIES = {
    'Attributes': 5,
    'Abilities_new': 2,
    'Abilities': 2,
    'Disciplines_new': 7,
    'Disciplines_clan': 7,
    'Disciplines_caitiff': 6,
    'Disciplines_other': 1000,
    'Disciplines_new_other': 1000,
    'Virtues': 1,
    'Humanity': 2,
    'Willpower': 1,
    'Backgrounds': 1
}

# Coûts en XP pour la méthode classique
XP_COST_CLASSIC = {
    'Attributes': 4,
    'Abilities_new': 3,
    'Abilities': 2,
    'Disciplines_new': 5,
    'Disciplines_clan': 5,
    'Disciplines_caitiff': 6,
    'Disciplines_other': 7,
    'Disciplines_new_other': 10,
    'Virtues': 1000,
    'Humanity': 2,
    'Willpower': 1,
    'Backgrounds': 1000
}

# Modèle de base pour les traits
BASE_TRAITS_TEMPLATE = {
    'Attributes': {
        'Physical': {'Strength': 1, 'Dexterity': 1, 'Stamina': 1},
        'Social': {'Charisma': 1, 'Manipulation': 1, 'Appearance': 1},
        'Mental': {'Perception': 1, 'Intelligence': 1, 'Wits': 1}
    },
    'Abilities': {
        'Talents': {'Alertness': 0, 'Athletics': 0, 'Brawl': 0,
                    'Empathy': 0, 'Expression': 0, 'Intimidation': 0,
                    'Intuition': 0, 'Leadership': 0, 'Streetwise': 0, 'Subterfuge': 0},
        'Skills': {'Animal Ken': 0, 'Crafts': 0, 'Drive': 0,
                   'Etiquette': 0, 'Firearms': 0, 'Larceny': 0,
                   'Melee': 0, 'Performance': 0, 'Stealth': 0, 'Survival': 0},
        'Knowledges': {'Academics': 0, 'Computer': 0, 'Finance': 0,
                       'Investigation': 0, 'Law': 0, 'Medicine': 0,
                       'Occult': 0, 'Politics': 0, 'Science': 0, 'Technology': 0}
    },
    'Disciplines': {
        'Animalism': 0, 'Auspex': 0, 'Celerity': 0, 'Chimerstry': 0,
        'Dementation': 0, 'Dominate': 0, 'Fortitude': 0, 'Necromancy': 0,
        'Obfuscate': 0, 'Obtenebration': 0, 'Potence': 0, 'Presence': 0,
        'Protean': 0, 'Quietus': 0, 'Serpentis': 0, 'Thaumaturgy': 0,
        'Vicissitude': 0, 'Valeren': 0
    },
    'Virtues': {'Conscience': 1, 'Self-Control': 1, 'Courage': 1},
    'Willpower': 0,
    'Backgrounds': {'Allies': 0, 'False Identity': 0, 'Contacts': 0,
                    'Domain': 0, 'Fame': 0, 'Influence': 0, 'Herd': 0,
                    'Resources': 0, 'Retainers': 0, 'Rituals': 0}
}

# Ponderation de base pour le calcul de l'objectif de fitness
BASE_PONDERATION = {
    'Attributes': {
        'Physical': {'Strength': 4, 'Dexterity': 4, 'Stamina': 4},
        'Social': {'Charisma': 0, 'Manipulation': 1, 'Appearance': 0},
        'Mental': {'Perception': 6, 'Intelligence': 6, 'Wits': 6}
    },
    'Abilities': {
        'Talents': {'Alertness': 2, 'Athletics': 2, 'Brawl': 2,
                    'Empathy': 2, 'Expression': 2, 'Intimidation': 2,
                    'Intuition': 2, 'Leadership': 2, 'Streetwise': 2, 'Subterfuge': 2},
        'Skills': {'Animal Ken': 1, 'Crafts': 1, 'Drive': 1,
                   'Etiquette': 1, 'Firearms': 1, 'Larceny': 1,
                   'Melee': 1, 'Performance': 1, 'Stealth': 1, 'Survival': 1},
        'Knowledges': {'Academics': 3, 'Computer': 3, 'Finance': 3,
                       'Investigation': 3, 'Law': 3, 'Medicine': 3,
                       'Occult': 3, 'Politics': 3, 'Science': 3, 'Technology': 3}
    },
    'Disciplines': {
        'Animalism': 0, 'Auspex': 0, 'Celerity': 0, 'Chimerstry': 0,
        'Dementation': 0, 'Dominate': 10, 'Fortitude': 5, 'Necromancy': 0,
        'Obfuscate': 0, 'Obtenebration': 0, 'Potence': 0, 'Presence': 3,
        'Protean': 0, 'Quietus': 0, 'Serpentis': 0, 'Thaumaturgy': 0,
        'Vicissitude': 0, 'Valeren': 0
    },
    'Virtues': {'Conscience': 1, 'Self-Control': 2, 'Courage': 3},
    'Willpower': 1,
    'Backgrounds': {'Allies': 0.1, 'False Identity': 0, 'Contacts': 0.1,
                    'Domain': 0.1, 'Fame': 0, 'Influence': 0.1, 'Herd': 0.1,
                    'Resources': 0.1, 'Retainers': 0.1, 'Rituals': 0}
}

# Disciplines de clan
CLAN_DISCIPLINES =  {
    'Animalism': 0, 'Auspex': 0, 'Celerity': 0, 'Chimerstry': 0,
    'Dementation': 0, 'Dominate': 1, 'Fortitude': 1, 'Necromancy': 0,
    'Obfuscate': 0, 'Obtenebration': 0, 'Potence': 0, 'Presence': 1,
    'Protean': 0, 'Quietus': 0, 'Serpentis': 0, 'Thaumaturgy': 0,
    'Vicissitude': 0, 'Valeren': 0
}

# Autres constantes
DEFAULT_TEMPERATURE = 2.0
DEFAULT_ALPHA = 0.999
MIN_TEMPERATURE = 0.1
LIMIT_CARAC = 5
LIMIT_CAPAC = 3
MUTATION_FACTOR = 32

GENERATION_LIMIT = {
    16: 5,
    15: 5,
    14: 5,
    13: 5,
    12: 5,
    11: 5,
    10: 5,
    9: 5,
    8: 5,
    7: 6,
    6: 7,
    5: 8,
    4: 9,
    3: 10,
}

def find_position_trait_in_dictionary(base_trait_name: str)->Union[list, None]:
    """
    Find the position of a trait in the BASE_TRAITS_TEMPLATE dictionary and return a list of keys to access it.
    For instance, if the base_trait_name is 'Strength', the function will return ['Attributes', 'Physical', 'Strength'].
    If the base_trait_name is "Academics", the function will return ['Abilities', 'Knowledges', 'Academics'].
    If the base_trait_name is "Willpower", the function will return ['Willpower']. etc.
    If the base_trait_name is not found, the function will return None.
    :param base_trait_name: The name of the trait to find
    :return: The position of the trait in the dictionary if it exists, None otherwise
    """

    def aux_find_position_trait_in_dictionary_rec(traits: dict, trait_name: str, keys: list)->Union[list, None]:
        for key, value in traits.items():
            if isinstance(value, dict):
                keys.append(key)
                result = aux_find_position_trait_in_dictionary_rec(value, trait_name, keys)
                if result:
                    return result
                keys.pop()
            elif key == trait_name:
                keys.append(key)
                return keys
        return None

    return aux_find_position_trait_in_dictionary_rec(BASE_TRAITS_TEMPLATE, base_trait_name, [])