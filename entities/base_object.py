class BaseObject:
    """
    Base pour tous les objets du jeu nécessitant un ID unique et un registre global.
    """

    _id_counter = {}
    _registry = {}

    def __init__(self, sprite_path: str = None):
        cls = self.__class__
        if cls not in BaseObject._id_counter:
            BaseObject._id_counter[cls] = 0
            BaseObject._registry[cls] = {}

        BaseObject._id_counter[cls] += 1
        self.id = BaseObject._id_counter[cls]
        BaseObject._registry[cls][self.id] = self
        self.sprite_path = sprite_path

    @classmethod
    def get_by_id(cls, id_):
        """
        Retourne l'objet correspondant à l'ID pour une classe donnée.
        """
        return BaseObject._registry.get(cls, {}).get(id_)

    @classmethod
    def all_instances(cls):
        """
        Retourne toutes les instances enregistrées pour une classe donnée.
        """
        return list(BaseObject._registry.get(cls, {}).values())
