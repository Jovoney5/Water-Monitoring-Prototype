"""
Water supplies data for all parishes
"""

def get_all_supplies():
    """Returns all water supplies with parish information"""
    return [
        # Westmoreland Supplies - 13 main source areas (47 monitoring locations)
        # Major Water Sources
        ('Roaring River I & II', 'treated', 'NWC', 'Savanna-la-Mar', 'Westmoreland'),
        ('Bullstrode', 'treated', 'NWC', 'Bullstrode', 'Westmoreland'),
        ('Dean\'s Valley', 'untreated', 'NWC', 'Dean\'s Valley', 'Westmoreland'),
        ('Carawina', 'untreated', 'NWC', 'Carawina', 'Westmoreland'),
        ('Williamsfield/Venture', 'untreated', 'NWC', 'Venture', 'Westmoreland'),
        ('Bluefields', 'treated', 'NWC', 'Bluefields', 'Westmoreland'),
        ('Jerusalem Mountains', 'untreated', 'PC', 'Jerusalem Mountains', 'Westmoreland'),
        ('Cave', 'untreated', 'PC', 'Cave', 'Westmoreland'),
        ('Friendship', 'untreated', 'PC', 'Friendship', 'Westmoreland'),
        ('Negril–Logwood', 'treated', 'NWC', 'Negril', 'Westmoreland'),
        ('Bethel Town/Cambridge', 'treated', 'NWC', 'Bethel Town', 'Westmoreland'),
        ('Paradise Farm', 'untreated', 'Private', 'Paradise Farm', 'Westmoreland'),
        ('Petersville', 'untreated', 'PC', 'Petersville', 'Westmoreland'),
        ('Dantrout', 'treated', 'NWC', 'Dantrout', 'Westmoreland'),

        # Trelawny Supplies
        # NWC Treated Supplies
        ('Rio Bueno', 'treated', 'NWC', 'Rio Bueno', 'Trelawny'),
        ('Duncans', 'treated', 'NWC', 'Duncans', 'Trelawny'),
        ('Falmouth', 'treated', 'NWC', 'Falmouth', 'Trelawny'),
        ('Wakefield', 'treated', 'NWC', 'Wakefield', 'Trelawny'),
        ('Bounty Hall', 'treated', 'NWC', 'Bounty Hall', 'Trelawny'),
        ('Springvale', 'treated', 'NWC', 'Springvale', 'Trelawny'),

        # PC Treated Supplies
        ('Albert Town', 'treated', 'PC', 'Albert Town', 'Trelawny'),
        ('Silver Sands', 'treated', 'PC', 'Silver Sands', 'Trelawny'),
        ('Lorrimers', 'treated', 'PC', 'Lorrimers', 'Trelawny'),
        ('Bengal', 'treated', 'PC', 'Bengal', 'Trelawny'),

        # PC Untreated Supplies
        ('Martha Brae', 'untreated', 'PC', 'Martha Brae', 'Trelawny'),
        ('Clarks Town', 'untreated', 'PC', 'Clarks Town', 'Trelawny'),
        ('Wait-a-Bit', 'untreated', 'PC', 'Wait-a-Bit', 'Trelawny'),
        ('Deeside', 'untreated', 'PC', 'Deeside', 'Trelawny'),
        ('Sherwood Content', 'untreated', 'PC', 'Sherwood Content', 'Trelawny'),
        ('Salem', 'untreated', 'PC', 'Salem', 'Trelawny'),
        ('Refuge', 'untreated', 'PC', 'Refuge', 'Trelawny'),
        ('Ulster Spring', 'untreated', 'PC', 'Ulster Spring', 'Trelawny'),
        ('Good Hope', 'untreated', 'PC', 'Good Hope', 'Trelawny'),
        ('Bunkers Hill', 'untreated', 'PC', 'Bunkers Hill', 'Trelawny'),
        ('Kettering', 'untreated', 'PC', 'Kettering', 'Trelawny'),
        ('Troy', 'untreated', 'PC', 'Troy', 'Trelawny'),
        ('Granville', 'untreated', 'PC', 'Granville', 'Trelawny'),
        ('Rock', 'untreated', 'PC', 'Rock', 'Trelawny'),
        ('Garlands', 'untreated', 'PC', 'Garlands', 'Trelawny'),

        # Private Supplies
        ('Harmony Cove Resort', 'treated', 'Private', 'Harmony Cove', 'Trelawny'),
        ('Grand Palladium Resort', 'treated', 'Private', 'Lucea', 'Trelawny'),
        ('Trelawny Beach Hotel', 'treated', 'Private', 'Falmouth', 'Trelawny'),
        ('Burwood Beach Resort', 'treated', 'Private', 'Burwood', 'Trelawny'),

        # Hanover Supplies
        # HMC Supplies (34 - All Untreated)
        ('Claremont Catchment', 'untreated', 'HMC', 'Claremont', 'Hanover'),
        ('Thompson Hill Catchment', 'untreated', 'HMC', 'Thompson Hill', 'Hanover'),
        ('Upper Rock Spring', 'untreated', 'HMC', 'Upper Rock Spring', 'Hanover'),
        ('Success Catchment', 'untreated', 'HMC', 'Success', 'Hanover'),
        ('Bamboo Spring', 'untreated', 'HMC', 'Bomboo', 'Hanover'),
        ('Jericho Spring', 'untreated', 'HMC', 'Jericho', 'Hanover'),
        ('Lethe Spring', 'untreated', 'HMC', 'Lethe', 'Hanover'),
        ('Welcome Spring', 'untreated', 'HMC', 'Welcome', 'Hanover'),
        ('Knockalva Catchment', 'untreated', 'HMC', 'Knocklava', 'Hanover'),
        ('Flamstead Spring', 'untreated', 'HMC', 'Flamstead', 'Hanover'),
        ('Pierces Village Catchment', 'untreated', 'HMC', 'Pierces Village', 'Hanover'),
        ('Cold Spring', 'untreated', 'HMC', 'Cold Spring', 'Hanover'),
        ('Rejion Tank', 'untreated', 'HMC', 'Rejoin', 'Hanover'),
        ('Rejoin Catchment', 'untreated', 'HMC', 'Rejoin', 'Hanover'),
        ('Chovey Hole', 'untreated', 'HMC', 'Askenish', 'Hanover'),
        ('Content Catchment', 'untreated', 'HMC', 'Content', 'Hanover'),
        ('St Simon Spring', 'untreated', 'HMC', 'St. Simon', 'Hanover'),
        ('Donalva Spring', 'untreated', 'HMC', 'Maryland', 'Hanover'),
        ('Sawpit Spring', 'untreated', 'HMC', 'Cove Road', 'Hanover'),
        ('Patty Hill Spring', 'untreated', 'HMC', 'Patty Hill', 'Hanover'),
        ('Woodsville Catchment', 'untreated', 'HMC', 'Woodsville', 'Hanover'),
        ('Dias Tank', 'untreated', 'HMC', 'Dias', 'Hanover'),
        ('Anderson Spring', 'untreated', 'HMC', 'Sandy Bay', 'Hanover'),
        ('Bamboo Roadside Overflow', 'untreated', 'HMC', 'Bamboo', 'Hanover'),
        ('Axe-and-Adze Catchment', 'untreated', 'HMC', 'Axe-And-Adze', 'Hanover'),
        ('Soja Spring', 'untreated', 'HMC', 'Retrieve', 'Hanover'),
        ('Castle Hyde Catchment', 'untreated', 'HMC', 'Castle Hyde', 'Hanover'),
        ('Medley Spring', 'untreated', 'HMC', 'Medley', 'Hanover'),
        ('Craig Nathan', 'untreated', 'HMC', 'Askenish', 'Hanover'),
        ('Jabez Catchment', 'untreated', 'HMC', 'Retieve', 'Hanover'),
        ('Rockfoot Reservoir', 'untreated', 'HMC', 'Askenish', 'Hanover'),
        ('Burntside Spring', 'untreated', 'HMC', 'Maryland', 'Hanover'),
        ('Old Cold Spring', 'untreated', 'HMC', 'Cold Spring', 'Hanover'),
        ('Spring Georgia', 'untreated', 'HMC', 'Georgia', 'Hanover'),

        # NWC Supplies (5 - All Treated)
        ('Logwood', 'treated', 'NWC', 'Logwood', 'Hanover'),
        ('New Milns', 'treated', 'NWC', 'New Milns', 'Hanover'),
        ('Kendal', 'treated', 'NWC', 'Kendal', 'Hanover'),
        ('Shettlewood Hanover', 'treated', 'NWC', 'Ramble', 'Hanover'),
        ('Great River - St. James', 'treated', 'NWC', 'St. James', 'Hanover'),

        # Private Supplies (18 - 16 Treated, 2 Untreated)
        ('Tryall Club', 'treated', 'Private', 'Sandy Bay', 'Hanover'),
        ('Vivid Water Store', 'treated', 'Private', 'Hopewell', 'Hanover'),
        ('Aquacity Water Store', 'treated', 'Private', 'Hopewell', 'Hanover'),
        ('M&B Water Store', 'treated', 'Private', 'Hopewell', 'Hanover'),
        ('Quenched Water Store', 'treated', 'Private', 'Lucea', 'Hanover'),
        ('Epic Blue', 'treated', 'Private', 'Lucea', 'Hanover'),
        ('Dynasty Water Store', 'treated', 'Private', 'Orange Bay', 'Hanover'),
        ('Valley Dew', 'untreated', 'Private', 'Miles Town, Ramble', 'Hanover'),
        ('Jus Chill', 'untreated', 'Private', 'Lethe', 'Hanover'),
        ('Royalton Resorts', 'treated', 'Private', 'Negril', 'Hanover'),
        ('Sandals Negril', 'treated', 'Private', 'Negril', 'Hanover'),
        ('Couples Negril', 'treated', 'Private', 'Negril', 'Hanover'),
        ('Sunset At The Palms', 'treated', 'Private', 'Negril', 'Hanover'),
        ('Azul Resort', 'treated', 'Private', 'Negril', 'Hanover'),
        ('Round Hill Resort', 'treated', 'Private', 'John Pringle drive, Hopewell', 'Hanover'),
        ('Hedonism II', 'treated', 'Private', 'Negril', 'Hanover'),
        ('Riu Tropical Bay', 'treated', 'Private', 'Negril', 'Hanover'),
        ('Riu Jamiecotel', 'treated', 'Private', 'Negril', 'Hanover'),
    ]