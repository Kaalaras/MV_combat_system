from entities.character import Character

class DefaultHuman(Character):
    """Default human character with no special abilities or traits."""
    def __init__(self) -> None:
        super().__init__(
            name="Default Human",
            clan="None",
            generation=0,
            archetype="None",
            traits={
    'Attributes': {
        'Physical': {'Strength': 2, 'Dexterity': 2, 'Stamina': 2},
        'Social': {'Charisma': 2, 'Manipulation': 2, 'Appearance': 2},
        'Mental': {'Perception': 2, 'Intelligence': 2, 'Wits': 2}
    },
    'Abilities': {
        'Talents': {'Alertness': 1, 'Athletics': 1, 'Brawl': 1,
                    'Empathy': 1, 'Expression': 1, 'Intimidation': 1,
                    'Intuition': 1, 'Leadership': 1, 'Streetwise': 1, 'Subterfuge': 1},
        'Skills': {'Animal Ken': 1, 'Crafts': 1, 'Drive': 1,
                   'Etiquette': 1, 'Firearms': 1, 'Larceny': 1,
                   'Melee': 1, 'Performance': 1, 'Stealth': 1, 'Survival': 1},
        'Knowledges': {'Academics': 1, 'Computer': 1, 'Finance': 1,
                       'Investigation': 1, 'Law': 1, 'Medicine': 1,
                       'Occult': 1, 'Politics': 1, 'Science': 1, 'Technology': 1}
    },
    'Disciplines': {
        'Animalism': 0, 'Auspex': 0, 'Celerity': 0, 'Chimerstry': 0,
        'Dementation': 0, 'Dominate': 0, 'Fortitude': 0, 'Necromancy': 0,
        'Obfuscate': 0, 'Obtenebration': 0, 'Potence': 0, 'Presence': 0,
        'Protean': 0, 'Quietus': 0, 'Serpentis': 0, 'Thaumaturgy': 0,
        'Vicissitude': 0, 'Valeren': 0
    },
    'Virtues': {'Conscience': 3, 'Self-Control': 4, 'Courage': 3},
    'Willpower': 0,
    'Backgrounds': {'Allies': 0, 'False Identity': 0, 'Contacts': 0,
                    'Domain': 0, 'Fame': 0, 'Influence': 0, 'Herd': 0,
                    'Resources': 0, 'Retainers': 0, 'Rituals': 0}
},
            clan_disciplines={},
            sprite_path="assets/sprites/characters/default_human.png"
        )
