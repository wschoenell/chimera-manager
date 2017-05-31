from distutils.core import setup

setup(
    name='chimera_supervisor',
    version='0.0.1',
    packages=['chimera_supervisor', 'chimera_supervisor.controllers', 'chimera_supervisor.controllers.scheduler',
              'chimera_supervisor.core', 'chimera_supervisor.controllers.scheduler.algorithms'],
    scripts=['scripts/chimera-supervisor', 'scripts/chimera-robobs'],
    url='http://github.com/astroufsc/chimera-supervisor',
    license='GPL v2',
    author='Tiago Ribeiro',
    author_email='tribeiro@ufs.br',
    description='Observatory manager for chimera.'
)
