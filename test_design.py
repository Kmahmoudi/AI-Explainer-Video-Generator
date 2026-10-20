"""Offline checks of the slide design, the artwork and the video command. Run: python -m unittest -v test_design.py

Drawing tests need Pillow (Arabic/Farsi shaping needs arabic-reshaper and python-bidi when Pillow has no RAQM); they are skipped without it.
No speech engine, FFmpeg or network is used.
"""
import copy
import json
import re
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
from unittest.mock import patch

import deck
import studio
import visuals

try:
    import PIL  # noqa: F401
except ImportError:  # pragma: no cover
    PIL = None

HERE = Path(__file__).resolve().parent


def slide(title='An idea', bullets=None, narration='A useful explanation of this topic.'):
    return {'title': title, 'bullets': bullets or ['A source point', 'Another source point'],
            'segments': [{'text': narration, 'emotion': 'warm', 'pause_ms': 200}]}


def story(n=4, lang='en'):
    seg = {'text': 'A short sentence for the voice to read aloud.', 'emotion': 'warm', 'pause_ms': 200}
    return {'version': 1, 'language': lang, 'title': 'A study of things', 'footer': 'Test footer', 'slides': [
        {'title': f'Slide {i + 1}', 'bullets': ['First point', 'Second point'], 'segments': [dict(seg), dict(seg, emotion='curious')]} for i in range(n)]}


def settings(**overrides):
    base = dict(title='A study of things', source='x' * 100, count=3, language='en', theme='vivid')
    return studio.validate_settings({**base, **overrides})


class PlanTests(unittest.TestCase):
    def test_every_video_has_a_cover_a_recap_and_variety(self):
        for n in (2, 3, 4, 6, 8, 20):
            plan = deck.plan(story(n), 'vivid')
            self.assertEqual(len(plan), n)
            self.assertEqual(plan[0]['layout'], 'cover')
            self.assertEqual(plan[-1]['layout'], 'recap')
            self.assertEqual({x['palette'] for x in plan}, {plan[0]['palette']})
            for a, b in zip(plan, plan[1:]):
                self.assertNotEqual(a['layout'], b['layout'])
                self.assertNotEqual(a['surface'], b['surface'])
            self.assertIsNone(plan[-1]['transition'])
            self.assertNotIn(None, [x['transition'] for x in plan[:-1]])
        plan = deck.plan(story(8), 'vivid')
        self.assertGreaterEqual(len({x['layout'] for x in plan}), 5)
        self.assertGreaterEqual(len({x['transition'] for x in plan[:-1]}), 4)

    def test_the_plan_is_repeatable_and_a_palette_and_theme_are_honoured(self):
        sb = story(6)
        self.assertEqual(deck.plan(sb, 'vivid'), deck.plan(copy.deepcopy(sb), 'vivid'))
        self.assertEqual({x['palette'] for x in deck.plan(sb, 'light', 'sunset')}, {'sunset'})
        self.assertTrue(all(x['surface'] in ('paper', 'tint', 'bold') for x in deck.plan(sb, 'light')))
        self.assertTrue(all(x['surface'] in ('deep', 'ink', 'bold') for x in deck.plan(sb, 'dark')))
        with self.assertRaises(ValueError):
            deck.plan(sb, 'neon')

    def test_layouts_that_need_several_points_are_not_given_to_slides_with_one(self):
        sb = story(8)
        for s in sb['slides']:
            s['bullets'] = s['bullets'][:1]
        for x in deck.plan(sb, 'vivid')[1:-1]:
            self.assertNotIn(x['layout'], ('cards', 'steps'))

    def test_directional_transitions_are_mirrored_for_right_to_left_languages(self):
        en = [x['transition'] for x in deck.plan(story(8, 'en'), 'vivid', seed=7)[:-1]]
        for lang in ('ar', 'fa'):
            rtl = [x['transition'] for x in deck.plan(story(8, lang), 'vivid', seed=7)[:-1]]
            self.assertEqual([deck.MIRROR.get(t, t) for t in en], rtl)
        self.assertTrue(set(deck.TRANSITIONS) >= set(en))

    def test_classic_templates_get_the_same_motion(self):
        plan = deck.motion_plan(story(5))
        self.assertEqual(len(plan), 5)
        self.assertIsNone(plan[-1]['transition'])
        self.assertNotIn(None, [x['transition'] for x in plan[:-1]])
        self.assertEqual(plan, deck.motion_plan(story(5)))

    def test_colours_have_readable_text_on_every_surface(self):
        for name, pal in deck.PALETTES.items():
            for surface in ('paper', 'tint', 'deep', 'ink', 'bold'):
                c = deck.surface_colors(pal, surface)
                self.assertGreater(abs(deck.luminance(c['bg']) - deck.luminance(c['ink'])), .45, (name, surface))
        self.assertEqual(deck.mix('#000000', '#ffffff', .5), '#808080')

    def test_the_footer_is_the_authors_or_a_tagline_in_the_lesson_language(self):
        self.assertEqual(deck.footer_text({'language': 'en', 'footer': ' My channel '}), 'My channel')
        for lang in ('en', 'ar', 'fa'):
            self.assertEqual(deck.footer_text({'language': lang, 'footer': ''}), deck.TAGLINES[lang])


class ContentTests(unittest.TestCase):
    def test_narration_changes_direction_without_changing_the_slide(self):
        sb = story(3)
        sb['slides'][1] = slide(narration='Solar panels convert sunlight into electricity.')
        original = copy.deepcopy(sb)
        self.assertEqual(deck.plan(sb)[1]['visual']['topic'], 'solar')
        self.assertEqual(sb, original)
        sb['slides'][1]['segments'][0]['text'] = 'The DNA molecule carries genetic information.'
        self.assertEqual(deck.plan(sb)[1]['visual']['topic'], 'biology')

    def test_local_slide_topic_beats_course_context(self):
        self.assertEqual(visuals.analyze(slide('Water', narration='Marine water and ocean life.'), 'Solar panel energy')['topic'], 'water')
        self.assertEqual(visuals.analyze(slide(), 'Solar panels')['topic'], 'solar')

    def test_intents_in_three_languages(self):
        samples = [
            (slide('Comparison', ['Solar collects light', 'Wind captures moving air']), 'comparison'),
            (slide('المقارنة', ['الطاقة الشمسية', 'طاقة الرياح'], 'نقارن بين المصدرين.'), 'comparison'),
            (slide('مقایسه', ['انرژی خورشیدی', 'انرژی باد'], 'این دو منبع را مقایسه می‌کنیم.'), 'comparison'),
            (slide('Installation steps', ['Inspect the site', 'Connect the system']), 'steps'),
            (slide('الخطوات', ['افحص الموقع', 'صل النظام'], 'هذه خطوات العمل.'), 'steps'),
            (slide('مراحل کار', ['محل را بازرسی کنید', 'سامانه را وصل کنید'], 'ابتدا بازرسی می‌کنیم، سپس وصل می‌کنیم.'), 'steps'),
            (slide('A definition', ['A cell is a basic unit of life']), 'focus'),
            (slide('An example', ['In this example, 20% is stored', 'The rest is used']), 'metric'),
        ]
        for content, layout in samples:
            with self.subTest(title=content['title']):
                sb = story(3)
                sb['slides'][1] = content
                self.assertEqual(deck.plan(sb)[1]['layout'], layout)

    def test_persian_topics_and_letter_variants(self):
        fa = visuals.analyze(slide('سلول‌ها', ['سلول‌های زنده'], 'سلول‌ها از مولکول‌ها ساخته شده‌اند.'))
        self.assertEqual((fa['topic'], fa['subject']), ('biology', 'cell'))
        self.assertEqual(visuals.analyze(slide('انرژی خورشیدی', narration='پنل‌ها نور خورشید را به برق تبدیل می‌کنند.'))['topic'], 'solar')
        self.assertEqual(visuals.normalize('كي'), visuals.normalize('کی'))

    def test_ambiguous_content_does_not_invent_relationships(self):
        for title in ('Two facts', 'An unrelated idea', 'Benefits', 'Research results'):
            result = visuals.analyze(slide(title))
            self.assertEqual(result['intent'], 'explain')
            self.assertIsNone(result['metric'])
        self.assertNotIn('steps', [s['layout'] for s in deck.plan(story(8))])

    def test_only_visible_percentages_are_highlighted(self):
        for value in ('20%', '٢٠٪', '12.5%', '20–30%', '≥ 30%'):
            text = f'In this example, {value} of the sample is affected.'
            self.assertEqual(visuals.analyze(slide(bullets=[text]))['metric'], {'value': value, 'text': text})
        self.assertIsNone(visuals.analyze(slide(narration='A percentage of 80% appears only in the narration.'))['metric'])

    def test_word_boundaries(self):
        self.assertEqual(visuals.topic_for('Fair repair', [], ''), 'abstract')
        self.assertEqual(visuals.topic_for('A heartfelt story', [], ''), 'abstract')

    def test_svg_contains_only_local_geometry_and_escaped_title(self):
        for subject in (*visuals.TOPICS, *visuals.SUBJECTS, 'abstract'):
            graphic = visuals.svg(visuals.scene(subject, ['#123456', '#456789', '#789abc']), '<script>alert(1)</script> & title')
            root = ET.fromstring(graphic)
            self.assertEqual(root.find('{http://www.w3.org/2000/svg}title').text, '<script>alert(1)</script> & title')
            self.assertTrue(all(node.tag.split('}')[-1] in {'svg', 'title', 'circle', 'rect', 'polyline'} for node in root.iter()))
            self.assertNotIn('href=', graphic)


@unittest.skipIf(PIL is None, 'Pillow is not installed')
class DrawingTests(unittest.TestCase):
    def draw(self, directory, board, index, **style):
        st = dict(deck.plan(board, 'vivid')[index - 1], **style)
        path = Path(directory) / 'slide.png'
        deck.draw_slide(board, board['slides'][index - 1], index, len(board['slides']), path, st, '720', studio.font_path)
        return path

    def test_every_layout_draws_in_three_languages_with_one_to_three_points(self):
        long = {'en': 'A rather long point that has to be wrapped over several lines to fit the space it is given on the slide',
                'ar': 'نقطة طويلة نسبيا يجب أن تلتف على عدة أسطر لتناسب المساحة المخصصة لها في الشريحة وتبقى مقروءة',
                'fa': 'نکته‌ای نسبتاً طولانی که باید در چند خط بشکند تا در فضای اسلاید جا شود و خوانا بماند'}
        with tempfile.TemporaryDirectory() as d:
            for lang in ('en', 'ar', 'fa'):
                for layout in deck.LAYOUT_FUNCS:
                    for n in (1, 2, 3):
                        sb = story(3, lang)
                        sb['slides'][1]['bullets'] = [long[lang] if i == 0 else f'Point {i + 1}' for i in range(n)]
                        try:
                            path = self.draw(d, sb, 2, layout=layout)
                        except ImportError:
                            self.skipTest('Arabic shaping libraries are not installed')
                        self.assertGreater(path.stat().st_size, 3000, (lang, layout, n))

    def test_text_that_cannot_fit_is_refused_by_the_design_code(self):
        sb = story(3)
        sb['slides'][1]['bullets'] = ['x' * 400]
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(deck.SlideError):
                self.draw(d, sb, 2, layout='cards')

    def test_a_layout_that_is_too_small_gives_way_to_a_roomier_one(self):
        project = {'id': '0' * 12, 'settings': settings(count=3), 'slides': [
            {'title': 'T' * 40, 'bullets': [('word ' * 36).strip()] * 4, 'segments': slide()['segments']} for _ in range(3)]}
        board = studio.storyboard(project)
        style = dict(deck.plan(board, 'vivid')[1], layout='focus')
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / 'a.png'
            studio.render_slide(project['slides'][1], project['settings'], 2, 3, path, board, style)
            self.assertTrue(path.exists())
            self.assertIn(style['layout'], ('rows', 'cards'))

    def test_deck_for_every_template_writes_slides_artwork_and_design(self):
        with tempfile.TemporaryDirectory() as tmp:
            for theme in studio.ALL_THEMES:
                project = {'id': '0' * 12, 'settings': settings(theme=theme, footer='Footer'), 'slides': story(3)['slides']}
                out = Path(tmp) / theme
                styles = studio.draw_deck(project, out)
                self.assertEqual(len(styles), 3)
                self.assertEqual(sorted(p.name for p in (out / 'slides').glob('*.png')), ['001.png', '002.png', '003.png'])
                self.assertEqual((out / 'slides' / '001.svg').exists(), theme in studio.DESIGNS)
                design = json.loads((out / 'design.json').read_text(encoding='utf-8'))
                self.assertEqual((design['theme'], design['visual_api_cost'], len(design['slides'])), (theme, 0, 3))
                self.assertIsNone(design['slides'][-1]['transition'])
            studio.contact_sheet(out, styles)
            self.assertTrue((out / 'contact-sheet.jpg').exists())

    def test_public_project_reports_the_design_of_every_slide(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(studio, 'PROJECTS', Path(tmp)):
            project = {'id': '0123456789ab', 'settings': settings(), 'slides': story(3)['slides'], 'status': 'draft'}
            studio.save_project(project)
            studio.draw_deck(project, studio.project_dir(project['id']))
            shown = studio.public_project(project)['slides']
            self.assertEqual([x['design']['layout'] for x in shown][0], 'cover')
            self.assertIsNone(shown[-1]['design']['transition'])


class VideoCommandTests(unittest.TestCase):
    def command(self, durations, theme='vivid', **options):
        timings = [{'duration': x, 'captions': []} for x in durations]
        board = story(len(durations))
        styles = deck.plan(board, theme) if theme in studio.DESIGNS else deck.motion_plan(board)
        cfg = settings(count=max(2, len(durations)), theme=theme, **options)
        return studio.video_command('ffmpeg', Path('project'), timings, styles, cfg), styles

    def test_transitions_end_when_the_next_slide_starts(self):
        durations = [6.0, 5.5, 7.25, 4.0]
        (args, total), styles = self.command(durations)
        self.assertAlmostEqual(total, sum(durations))
        graph = args[args.index('-filter_complex') + 1]
        tr = studio.transition_length(durations)
        self.assertEqual(tr, .5)
        offsets = [float(x) for x in re.findall(r'offset=([0-9.]+)', graph)]
        self.assertEqual(offsets, [round(sum(durations[:i]) - tr, 4) for i in (1, 2, 3)])
        self.assertEqual(graph.count('xfade='), 3)
        for style in styles[:-1]:
            self.assertIn(f'transition={style["transition"]}', graph)
        self.assertEqual([float(x) for x in re.findall(r"-t', '([0-9.]+)", repr(args))], [6.0, 6.0, 7.75, 4.5])
        self.assertEqual(args[args.index('-map') + 1], '[x3]')
        self.assertIn('fade=t=in', graph)
        self.assertIn('fade=t=out', graph)
        self.assertIn('eval=frame', graph)

    def test_classic_templates_move_too(self):
        (args, _), _ = self.command([4.0, 4.0, 4.0], theme='midnight')
        graph = args[args.index('-filter_complex') + 1]
        self.assertEqual(graph.count('xfade='), 2)
        self.assertIn('eval=frame', graph)

    def test_without_transitions_slides_are_cut_and_without_motion_there_is_no_zoom(self):
        (args, total), _ = self.command([3.0, 3.0, 3.0], transitions=False, motion=False)
        graph = args[args.index('-filter_complex') + 1]
        self.assertIn('concat=n=3', graph)
        self.assertNotIn('xfade', graph)
        self.assertNotIn('eval=frame', graph)
        self.assertEqual(total, 9.0)

    def test_a_very_short_slide_gets_no_transition_instead_of_a_broken_one(self):
        self.assertEqual(studio.transition_length([5.0]), 0.0)
        self.assertEqual(studio.transition_length([5.0, .1]), 0.0)
        self.assertAlmostEqual(studio.transition_length([5.0, 1.0]), 10 / 24)

    def test_resolution_sets_the_frame_size(self):
        (args, _), _ = self.command([3.0, 3.0], resolution='1080')
        self.assertIn('crop=1920:1080', args[args.index('-filter_complex') + 1])

    def test_narration_leaves_a_quiet_end_so_the_transition_falls_in_silence(self):
        try:
            import numpy as np
        except ImportError:
            self.skipTest('NumPy is not installed')
        rate = 24000
        with tempfile.TemporaryDirectory() as tmp, patch.object(studio, 'PROJECTS', Path(tmp)), patch.object(studio, 'synthesize_azure', return_value=(np.ones(rate, dtype=np.float32) * .3, rate)):
            cfg = settings(count=2, voice_engine='azure')
            project = {'id': '0123456789ab', 'settings': cfg, 'slides': [dict(s, segments=[dict(s['segments'][0], pause_ms=180)]) for s in story(2)['slides']]}
            studio.save_project(project)
            timings = studio.speech_audio(project, {'cancel': False, 'log': [], 'progress': 0}, {})
        self.assertGreater(timings[0]['duration'] - (.12 + 1.0 + .18), studio.TAIL_SILENCE - .02)


class StoryboardFileTests(unittest.TestCase):
    def test_the_examples_are_valid_and_free_of_site_branding(self):
        for name in ('solar-lesson-en.json', 'solar-lesson-ar.json'):
            settings_, slides = studio.read_storyboard(HERE / 'examples' / name)
            self.assertEqual(len(slides), settings_['count'])
            self.assertEqual(settings_['footer'], 'Explainer Studio')

    def test_a_bad_storyboard_is_refused_with_a_reason(self):
        with tempfile.TemporaryDirectory() as tmp:
            for content in ('{"version": 2, "slides": []}', '[]', '{"version": 1, "slides": [{"title": "x"}], "title": "t"}'):
                path = Path(tmp) / 'bad.json'
                path.write_text(content, encoding='utf-8')
                with self.assertRaises(ValueError):
                    studio.read_storyboard(path)

    def test_import_makes_a_project_with_the_chosen_template(self):
        project = studio.storyboard_project(HERE / 'examples' / 'solar-lesson-ar.json', theme='dark', palette='forest')
        self.assertEqual((project['settings']['theme'], project['settings']['palette'], project['settings']['language']), ('dark', 'forest', 'ar'))
        self.assertEqual(project['status'], 'draft')
        self.assertRegex(project['id'], r'^[a-f0-9]{12}$')


if __name__ == '__main__':
    unittest.main()
