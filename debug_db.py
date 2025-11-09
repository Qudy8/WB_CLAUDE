"""Debug database issue."""
from app import app
from models import db

with app.app_context():
    print('Database engine:', db.engine)
    print('Database URL:', db.engine.url)
    print('\nMetadata tables:')
    for table in db.metadata.tables:
        print(f'  - {table}')

    print(f'\nTotal tables in metadata: {len(db.metadata.tables)}')

    if len(db.metadata.tables) > 0:
        print('\nAttempting to create tables...')
        db.create_all()
        print('Done!')
    else:
        print('\nNo tables found in metadata! Models not registered.')
