import os, sys, unittest
CURRENT_DIR = os.path.dirname(__file__)
PACKAGE_ROOT = os.path.abspath(os.path.join(CURRENT_DIR, '..', '..'))
if PACKAGE_ROOT not in sys.path:
    sys.path.insert(0, PACKAGE_ROOT)

from entities.armor import Armor

class TestArmorPrecedence(unittest.TestCase):
    def test_severity_and_all(self):
        armor = Armor(name='SeverityAll', armor_value=0, damage_type=['superficial'], weapon_type_protected=['brawl'],
                      resistance_multipliers={'superficial':2.0,'all':1.5})
        # multiplier = 2.0 * 1.5 = 3.0
        self.assertEqual(armor.modify_incoming(4, 'superficial'), 12)

    def test_category_and_all(self):
        armor = Armor(name='CategoryAll', armor_value=0, damage_type=['superficial'], weapon_type_protected=['brawl'],
                      resistance_multipliers={'fire':0.5,'all':2.0})
        # classify('fire') => sev unknown, cat fire -> 0.5 * 2.0 = 1.0
        self.assertEqual(armor.modify_incoming(10, 'fire'), 10)

    def test_category_immunity_overrides_all(self):
        armor = Armor(name='ImmuneFire', armor_value=0, damage_type=['superficial'], weapon_type_protected=['brawl'],
                      resistance_multipliers={'fire':0.0,'all':2.0})
        self.assertEqual(armor.modify_incoming(12, 'fire'), 0)

    def test_no_matching_keys_returns_original(self):
        armor = Armor(name='Neutral', armor_value=0, damage_type=['superficial'], weapon_type_protected=['brawl'],
                      resistance_multipliers={'cold':0.5})
        self.assertEqual(armor.modify_incoming(7, 'superficial'), 7)

if __name__ == '__main__':
    unittest.main(verbosity=2)
