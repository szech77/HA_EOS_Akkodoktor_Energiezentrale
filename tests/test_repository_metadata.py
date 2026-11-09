"""Validate branch licenses and non-destructive GitHub metadata setup."""
import json
from pathlib import Path
import shutil
import unittest

from tools.validate_hacs_metadata import apply_metadata, repository_metadata, validate
from test_energy import temporary_project_directory

ROOT = Path(__file__).resolve().parents[1]


class RepositoryMetadataRequirements(unittest.TestCase):
    def project(self, directory):
        for relative in ('LICENSE','custom_components/eos_energiezentrale/LICENSE',
                         '.github/repository-metadata.json'):
            target = directory / relative
            target.parent.mkdir(parents=True,exist_ok=True)
            shutil.copy2(ROOT / relative,target)

    def test_complete_license_is_valid_even_without_github_repository_recognition(self):
        with temporary_project_directory() as directory:
            self.project(directory)
            license = directory / 'LICENSE'
            original = license.read_text(encoding='utf-8')
            license.write_bytes(('\n'+original.strip()+'\n').replace('\n','\r\n').encode())
            validate(directory)

    def test_missing_or_noncommercial_license_blocks_validation(self):
        for relative in ('LICENSE','custom_components/eos_energiezentrale/LICENSE'):
            for invalid in ('', 'For private non-commercial use only.'):
                with self.subTest(relative=relative,invalid=invalid), temporary_project_directory() as directory:
                    self.project(directory)
                    (directory / relative).write_text(invalid,encoding='utf-8')
                    with self.assertRaises(ValueError):
                        validate(directory)

    def test_incomplete_or_invalid_github_metadata_is_rejected(self):
        for description,topics in (('', ['hacs']), ('Energy',[]), ('Energy',['Not a topic']),
                                    ('Energy',['hacs','hacs'])):
            with self.subTest(description=description,topics=topics), temporary_project_directory() as directory:
                self.project(directory)
                (directory / '.github/repository-metadata.json').write_text(
                    json.dumps({'description':description,'topics':topics}),encoding='utf-8')
                with self.assertRaises(ValueError):
                    repository_metadata(directory)

    def api(self, description='', topics=(), apply=True):
        state = {'description':description,'topics':list(topics),'writes':[]}
        def api(path='',method='GET',data=None):
            if method != 'GET':
                state['writes'].append((path,method,data))
                if apply:
                    if path == '/topics':
                        state['topics'] = data['names']
                    else:
                        state['description'] = data['description']
            return {'names':list(state['topics'])} if path == '/topics' else {'description':state['description']}
        return api,state

    def test_missing_metadata_is_applied_verified_and_repeatable(self):
        api,state = self.api(topics=['existing-topic'])
        desired = {'description':'EOS energy management','topics':['hacs','home-assistant']}
        apply_metadata(api,desired)
        self.assertEqual(state['description'],desired['description'])
        self.assertEqual(set(state['topics']),{'existing-topic','hacs','home-assistant'})
        writes = list(state['writes'])
        apply_metadata(api,desired)
        self.assertEqual(state['writes'],writes)

    def test_maintainer_description_and_topics_are_preserved(self):
        api,state = self.api(description='Maintainer description',topics=['custom-topic'])
        apply_metadata(api,{'description':'Default description','topics':['hacs']})
        self.assertEqual(state['description'],'Maintainer description')
        self.assertEqual(set(state['topics']),{'custom-topic','hacs'})
        self.assertFalse(any(method == 'PATCH' for _,method,_ in state['writes']))

    def test_topic_limit_or_unconfirmed_change_does_not_report_success(self):
        api,state = self.api(topics=['topic-'+str(i) for i in range(20)])
        with self.assertRaises(ValueError):
            apply_metadata(api,{'description':'Energy','topics':['hacs']})
        self.assertEqual(state['writes'],[])
        api,state = self.api(apply=False)
        with self.assertRaises(ValueError):
            apply_metadata(api,{'description':'Energy','topics':['hacs']})
