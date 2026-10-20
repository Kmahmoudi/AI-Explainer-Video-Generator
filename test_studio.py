"""Offline regression checks. Run: python -m unittest -v test_studio.py

Provider doubles test pipeline contracts; these do not establish real model quality.
"""
import copy
import io
import json
from pathlib import Path
import tempfile
import types
import unittest
from unittest.mock import patch
import wave

import studio


def settings(**overrides):
    return studio.validate_settings(dict(title='How a home EMS works',source='A controller measures service current and allocates capacity. It reduces electric vehicle charging current when household demand rises. Local control continues without internet.',count=2,**overrides))


def slide(text='The controller measures current, then allocates capacity.'):
    return {'title':'Understand the flow','bullets':['Measure demand','Allocate capacity'],
            'segments':[{'text':text,'emotion':'warm','pause_ms':180,'breath':False},
                        {'text':'Now we can connect that idea to charging.','emotion':'curious','pause_ms':120,'breath':True}]}


class StudioTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.root=Path(self.temp.name)
        self.paths=patch.multiple(studio,PROJECTS=self.root/'projects',MODELS=self.root/'models')
        self.paths.start()
        self.job={'cancel':False,'log':[],'progress':0}
        self.project={'id':'123456abcdef','settings':settings(),'slides':[slide(),slide()],'status':'draft'}
        studio.save_project(self.project)

    def tearDown(self):
        self.paths.stop()
        self.temp.cleanup()

    def test_settings_boundaries_and_language(self):
        for language in ('en','ar','fa'):
            self.assertEqual(settings(language=language)['language'],language)
        for theme in studio.ALL_THEMES:
            self.assertEqual(settings(theme=theme)['theme'],theme)
        self.assertEqual(settings()['palette'],'auto')
        self.assertTrue(settings()['transitions'] and settings()['motion'])
        self.assertEqual(settings(footer='  My   channel ')['footer'],'My channel')
        for values in ({'language':'xx'},{'pace':2},{'resolution':'4k'},{'voice_engine':'shell'},{'theme':'neon'},{'palette':'plaid'},{'footer':'x'*121}):
            with self.assertRaises(ValueError):settings(**values)
        data=settings();data['count']=21
        with self.assertRaises(ValueError):studio.validate_settings(data)

    def test_slide_validation_rejects_bad_metadata(self):
        for language_text in ('A clear explanation.','شرح واضح للأفكار.','توضیح روشن درباره موضوع.'):
            self.assertEqual(studio.validate_slide(slide(language_text))['segments'][0]['text'],language_text)
        bad=slide();bad['segments'][0]['emotion']='warm|curious'
        with self.assertRaises(ValueError):studio.validate_slide(bad)
        bad=slide();bad['segments'][0]['pause_ms']=-1
        with self.assertRaises(ValueError):studio.validate_slide(bad)
        bad=slide();bad['bullets']=['x'*181]
        with self.assertRaises(ValueError):studio.validate_slide(bad)

    def test_source_chunking_covers_all_words(self):
        source=' '.join(f'fact{i}' for i in range(1200))
        chunks=studio.source_chunks(source)
        self.assertEqual(' '.join(chunks),source)
        self.assertTrue(all(len(x)<=1800 for x in chunks))

    def test_paths_cannot_escape_project_root(self):
        for path in ('../other','a/b','A'*12,'a'*13,'C:\\Windows'):
            with self.assertRaises(ValueError):studio.project_dir(path)

    def test_unicode_project_roundtrip_and_no_secret_fields(self):
        self.project['slides'][0]['title']='فارسی و العربية'
        studio.save_project(self.project)
        self.assertEqual(studio.load_project(self.project['id']),self.project)
        self.assertNotIn('azure_key',json.dumps(self.project))

    def test_cancel_stops_before_provider_work(self):
        self.job['cancel']=True
        with self.assertRaises(studio.Cancelled):studio.llm_json('anything',studio.MODEL,self.job)

    def test_llm_retries_invalid_json_and_caps_memory(self):
        responses=[{'message':{'content':'not-json'}},{'message':{'content':'{"ok":true}'}}]
        with patch.object(studio,'request_json',side_effect=responses) as request:
            self.assertEqual(studio.llm_json('prompt',studio.MODEL,self.job),{'ok':True})
        payload=request.call_args.args[1]
        self.assertEqual(payload['options']['num_ctx'],4096)
        self.assertEqual(payload['options']['num_gpu'],0)
        self.assertNotIn('think',payload)

    def test_writing_pipeline_connects_to_previous_narration(self):
        replies=[{'note':'A local controller measures current and controls charging.'},
                 {'slides':[{'title':'Measure demand','source_ids':[1]},{'title':'Control charging','source_ids':[1]}]},
                 slide('First, measurement gives us a picture of household demand.'),
                 slide('Building on that measurement, we can allocate charging capacity.')]
        with patch.object(studio,'ensure_ollama'),patch.object(studio,'request_json',return_value={'models':[{'name':studio.MODEL}]}),patch.object(studio,'llm_json',side_effect=replies) as llm,patch.object(studio,'unload_model') as unload,patch.object(studio,'render_slides'):
            studio.plan_project(self.project,self.job)
        self.assertEqual(len(self.project['slides']),2)
        self.assertIn('First, measurement',llm.call_args_list[-1].args[0])
        unload.assert_called()
        self.assertEqual(studio.load_project(self.project['id'])['status'],'draft')

    def test_failed_script_releases_model(self):
        with patch.object(studio,'ensure_ollama'),patch.object(studio,'request_json',return_value={'models':[{'name':studio.MODEL}]}),patch.object(studio,'llm_json',side_effect=RuntimeError('provider failed')),patch.object(studio,'unload_model') as unload:
            with self.assertRaisesRegex(RuntimeError,'provider failed'):
                studio.plan_project(self.project,self.job)
        unload.assert_called_once_with(studio.MODEL)

    def test_audio_and_pcm_join_have_consistent_durations(self):
        try:
            import numpy as np
        except ImportError:
            self.skipTest('NumPy is not installed')
        self.project['settings']['voice_engine']='azure'
        self.project['settings']['breaths']=True
        audio=np.sin(np.arange(4800)*.08).astype(np.float32)*.2
        with patch.object(studio,'synthesize_azure',return_value=(audio,24000)):
            timings=studio.speech_audio(self.project,self.job,{})
        directory=studio.project_dir(self.project['id'])
        total_frames=0
        for i,timing in enumerate(timings):
            with wave.open(str(directory/'audio'/f'{i+1:03}.wav'),'rb') as wav:
                self.assertEqual(wav.getframerate(),24000)
                self.assertAlmostEqual(timing['duration'],wav.getnframes()/24000)
                self.assertAlmostEqual(timing['duration']*24,round(timing['duration']*24),places=4)
                total_frames+=wav.getnframes()
            self.assertLess(timing['captions'][-1]['end'],timing['duration'])
        (directory/'slides').mkdir()
        for i in range(2):(directory/'slides'/f'{i+1:03}.png').write_bytes(b'test-placeholder')
        commands=[]
        def encoder(args,log_path,job,cwd=None,on_time=None):
            commands.append(args)
            if on_time:on_time(1.0)
            Path(args[-1]).write_bytes(b'mocked-mp4')
        module=types.SimpleNamespace(get_ffmpeg_exe=lambda:'ffmpeg')
        with patch.dict('sys.modules',{'imageio_ffmpeg':module}),patch.object(studio,'run_process',side_effect=encoder):
            studio.compose_video(self.project,timings,self.job)
        with wave.open(str(directory/'narration.wav'),'rb') as wav:
            self.assertEqual(wav.getnframes(),total_frames)
        self.assertTrue((directory/'captions.srt').exists())
        self.assertTrue((directory/'project-export.zip').exists())
        self.assertEqual(len(commands),1)       # the whole video is one FFmpeg run
        self.assertIn('xfade',commands[0][commands[0].index('-filter_complex')+1])
        self.assertIn(str(directory/'narration.wav'),commands[0])
        self.assertEqual(self.project['status'],'complete')

    def test_empty_speech_fails_instead_of_silent_video(self):
        try:
            import numpy as np
        except ImportError:
            self.skipTest('NumPy is not installed')
        self.project['settings']['voice_engine']='azure'
        with patch.object(studio,'synthesize_azure',return_value=(np.zeros(4000),24000)):
            with self.assertRaisesRegex(RuntimeError,'empty or invalid'):
                studio.speech_audio(self.project,self.job,{})

    def test_timestamp_rollover(self):
        self.assertEqual(studio.caption_stamp(3661.234),'01:01:01,234')
        self.assertEqual(studio.caption_stamp(59.9999,'.'),'00:01:00.000')

    def test_failed_project_does_not_offer_stale_video(self):
        directory=studio.project_dir(self.project['id'])
        (directory/'video.mp4').write_bytes(b'old')
        self.project['status']='error'
        self.assertEqual(studio.public_project(self.project)['assets'],{})
        self.project['status']='complete'
        self.assertIn('video.mp4',studio.public_project(self.project)['assets'])

    def test_embedded_ui_references_and_placeholders(self):
        import re
        from html.parser import HTMLParser
        class Page(HTMLParser):
            ids=[]
            external=[]
            def handle_starttag(self,tag,attrs):
                attrs=dict(attrs)
                if 'id' in attrs:self.ids.append(attrs['id'])
                if tag=='script' and 'src' in attrs:self.external.append(attrs['src'])
        page=Page();page.feed(studio.UI)
        self.assertEqual(len(page.ids),len(set(page.ids)))
        self.assertFalse(page.external)
        self.assertTrue(set(re.findall(r"\$\('([^']+)'\)",studio.UI))<=set(page.ids))
        self.assertIn('__TOKEN__',studio.UI)
        self.assertIn('__MODEL__',studio.UI)
        self.assertIn('__PALETTES__',studio.UI)


if __name__=='__main__':
    unittest.main()
