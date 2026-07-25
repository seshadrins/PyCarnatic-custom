import sf2_loader as sf2
import pygame
import musicpy as mp
import os
import math
import time
import threading
from midiutil.MidiFile import MIDIFile, TICKSPERQUARTERNOTE
from carnatic import cparser,settings, thaaLa#,midi2audio
_PYGAME_FINISH_CLOCK_SECONDS = 30
FREQ_FACTOR_1 = 4096/math.log(2)
FREQ_FACTOR = FREQ_FACTOR_1*math.log(2.0**(1.0/6.0))
sf_player = None
class MPlayer(sf2.sf2_loader):
    def __init__(self,sound_font_file=settings._SOUND_FONT_FILE):
        super().__init__()
        self.is_playing = False
        self.is_paused = False
        self._playback_lock = threading.Lock()
        self._playback_generation = 0
        self.loader = sf2.sf2_loader(file=sound_font_file)
        # Initialise pygame once here on the main thread.
        pygame.init()
    def start(self):
        # pygame is already initialised in __init__; nothing more needed here.
        self.is_playing = False
    def play_midi_file(self, midi_file, on_audio_start=None):
        """Synthesise and play a MIDI file.

        sf2_loader.play_midi_file performs *offline synthesis* (export_midi_file)
        before any audio is emitted, which can take several hundred milliseconds.
        To allow callers to capture ``_play_start_time`` at the exact moment audio
        begins (rather than at the start of synthesis), pass an optional
        ``on_audio_start`` callback.  It is invoked on the background thread
        immediately before pygame starts emitting samples.
        """
        if not os.path.exists(midi_file):
            raise FileNotFoundError("midi file: " + midi_file + ' does not exist')
        with self._playback_lock:
            self._playback_generation += 1
            playback_generation = self._playback_generation
        self.is_playing = True
        self.is_paused = False
        print('synthesising midi file', midi_file)
        # Step 1 – offline synthesis (slow: renders the whole piece to a WAV buffer)
        audio = self.loader.export_midi_file(midi_file, get_audio=True)
        # STOP may be pressed while the MIDI is being rendered.  In that case
        # there is no mixer channel to stop yet, so do not start the sound after
        # rendering completes.
        with self._playback_lock:
            if playback_generation != self._playback_generation:
                self.is_playing = False
                self.is_paused = False
                return
        # Step 2 – notify caller that audio is about to start
        if on_audio_start is not None:
            on_audio_start()
        print('playing midi file', midi_file)
        # Step 3 – start playback (non-blocking)
        import sf2_loader as _sf2
        _sf2.play_sound(audio, wait=False)
        # Wait for playback to finish.  pygame.time.delay() can monopolise the
        # Python interpreter on Windows and temporarily freeze Qt's UI thread,
        # even though mixer playback continues.  time.sleep() releases the GIL.
        # pygame.event.poll() must also not be called from a background thread.
        while mp.pygame.mixer.get_busy():
            time.sleep(0.01)
        self.is_playing = False
        self.is_paused = False
        print('playing finished')
    def play_audio_file(self,audio_file):
        audio_file = os.path.abspath(audio_file)
        if not os.path.exists(audio_file):
            assert "midi file:"+audio_file+' does not exist'
        self.start()
        pygame.mixer.music.load(audio_file)
        pygame.mixer.music.play(-1)
        print('playing',audio_file,pygame.mixer.get_busy())
        assert pygame.mixer.get_busy()==True,"Mixer not working"
        import musicpy as mp
        while mp.mixer.get_busy():
            print('playing')
            pygame.time.delay(10)
            pygame.event.poll()
        print('playing finished')
    def pause(self):
        #print('cmidi pause',self.is_playing)
        if self.is_playing:
            self.loader.pause()
            self.is_playing = False
            self.is_paused = True
            #print('cmidi paused',self.is_playing)
    def resume(self):
        #print('cmidi resume',self.is_playing)
        if self.is_paused:
            self.loader.unpause()
            self.is_playing = True
            self.is_paused = False
            #print('cmidi resumed',self.is_playing)
    def stop(self):
        # Invalidate playback even when audio is paused or still being
        # synthesised, then stop any channel which is already active.
        with self._playback_lock:
            self._playback_generation += 1
        self.loader.stop()
        self.is_playing = False
        self.is_paused = False
    def save_as_mp3(self,midi_file,mp3_file):
        self.loader.export_midi_file(midi_file,name=mp3_file, format='mp3', export_args={'bitrate': '320k'})       
def _get_time_in_beats(time_in_sec):
    beats_per_second = (settings.TEMPO/60)
    time_in_beats = time_in_sec * beats_per_second
    return time_in_beats
def _pitch_to_midi_pitch_bend(pitch:float):
    """ pitchBend=(int)(PITCH_BEND_MAX+4096*Math.log(c16_freq_ratio[wInd])/Math.log(2)); """
    pitch_bend = 4096 * 12 * math.log2(pitch/70)
    return pitch_bend
def write_to_midifile_from_scamp_notes(scamp_note_list,midi_file_name = 'output.mid',include_percussion_layer=False,solkattu_list=None):
    #print(scamp_note_list)
    track_max = 1
    if include_percussion_layer:
        track_max = 2    
    #print('include percussion layer',include_percussion_layer,track_max)
    # Quantize cumulative boundaries, rather than independently truncating
    # every start time and duration. Fractional speeds such as 0.5 produce
    # irrational beat durations; independent conversion can otherwise leave
    # intermittent one-tick holes between consecutive notes.
    midi_file = MIDIFile(
        numTracks=track_max,
        ticks_per_quarternote=TICKSPERQUARTERNOTE,
        eventtime_is_ticks=True)
    for t in range(track_max):
        midi_file.addTrackName(track=t, time=0, trackName='sample track-'+str(t))
        midi_file.addTempo(track=t, time=0, tempo=settings.TEMPO)
    cumulative_beats = 0.0
    cumulative_tick = 0
    melody_channel = 0
    previous_midi_pitch = None
    if len(scamp_note_list)==0:
        return
    for note,(instrument, pitch,durn) in scamp_note_list:
        instrument_index = instrument # instrument_list.index(instrument)
        duration_beats = durn
        start_tick = cumulative_tick
        cumulative_beats += duration_beats
        end_tick = round(cumulative_beats * TICKSPERQUARTERNOTE)
        duration_ticks = max(1, end_tick - start_tick)
        cumulative_tick = start_tick + duration_ticks
        if note=='$':
            instrument_index = len(settings._ALL_INSTRUMENTS)+1
            previous_midi_pitch = None
            continue
        midi_pitch = round(pitch)
        # Some SoundFont renderers occasionally suppress a same-channel
        # retrigger when identical pitches meet at fractional-speed tick
        # boundaries. Alternate two melody channels for an immediately
        # repeated pitch so each Note Off is isolated from the next Note On.
        if midi_pitch == previous_midi_pitch:
            melody_channel = 1 - melody_channel
        else:
            melody_channel = 0
        midi_file.addProgramChange(
            0, channel=melody_channel, time=start_tick,
            program=instrument_index)
        midi_file.addNote(
            track=0, channel=melody_channel, pitch=midi_pitch,
            time=start_tick,
            duration=duration_ticks,
            volume=settings._INSTRUMENT_VOLUME_LEVELS[instrument_index])
        previous_midi_pitch = midi_pitch
    if include_percussion_layer and solkattu_list is not None:
        cumulative_beats = 0.0
        cumulative_tick = 0
        for beat_name, (instrument, pitch, durn) in solkattu_list:
            instrument_index = instrument
            duration_beats = durn
            start_tick = cumulative_tick
            cumulative_beats += duration_beats
            end_tick = round(cumulative_beats * TICKSPERQUARTERNOTE)
            duration_ticks = max(1, end_tick - start_tick)
            cumulative_tick = start_tick + duration_ticks
            if beat_name == '$':
                continue
            # Use channel 9 for percussion (GM standard) on track 1
            midi_file.addProgramChange(
                1, channel=9, time=start_tick, program=instrument_index)
            midi_file.addNote(track=1, channel=9, pitch=round(pitch),
                              time=start_tick, duration=duration_ticks,
                              volume=100)
    with open(midi_file_name, 'wb') as binfile:
        midi_file.writeFile(binfile)
def _play_music(music_file):
    """
    stream music with mixer.music module in blocking manner
    this will stream the sound from disk while playing
    """
    clock = pygame.time.Clock()
    try:
        pygame.mixer.music.load(music_file)
        print("Music file %s loaded!" % music_file)
    except pygame.error:
        print("File %s not found! (%s)" % (music_file, pygame.get_error()))
        return
    pygame.mixer.music.play()
    while pygame.mixer.music.get_busy():
        # check if playback has finished
        clock.tick(_PYGAME_FINISH_CLOCK_SECONDS)
def play_midi_file(midi_file):
    print('loading soundfont',settings._SOUND_FONT_FILE)
    loader = sf2.sf2_loader(settings._SOUND_FONT_FILE)
    print('loader channel info',loader.channel_info())
    insts = loader.all_instruments(max_bank=129, max_preset=128, sfid=None, hide_warnings=True)
    print('all instruments',insts)
    print('playing midi file',midi_file)
    pygame.init()
    loader.play_midi_file(midi_file)
    while mp.pygame.mixer.get_busy():
        pygame.time.delay(10)
        pygame.event.poll()
    print('player stopped on its own')
def play_midi_file_1(midi_file):
    freq = 44100    # audio CD quality
    bitsize = -16   # unsigned 16 bit
    channels = 2    # 1 is mono, 2 is stereo
    buffer = 1024    # number of samples
    pygame.mixer.init(freq, bitsize, channels, buffer)
    
    # optional volume 0 to 1.0
    #pygame.mixer.music.set_volume(1.0) # Max Volume V1.0.2
    try:
        _play_music(midi_file)
    except KeyboardInterrupt:
        # if user hits Ctrl/C then exit
        # (works only in console mode)
        pygame.mixer.music.fadeout(1000)
        pygame.mixer.music.stop()
        raise SystemExit
def _write_to_midi_and_play(scamp_note_list,include_percussion_layer=False,solkattu_list=None):
    temp_midi_file = settings._TEMP_PATH+'output.mid' 
    write_to_midifile_from_scamp_notes(scamp_note_list,temp_midi_file,include_percussion_layer=include_percussion_layer,solkattu_list=solkattu_list)
    #print('mplayer initiated')
    sfp = MPlayer(settings._SOUND_FONT_FILE)
    sfp.play_midi_file(temp_midi_file)
    #print('mplayer returned')
    return sfp
def play_solkattu(scamp_note_list):
    _write_to_midi_and_play(scamp_note_list,include_percussion_layer=False)    
def play_notes_from_file(notation_file,include_percussion_layer=False):
    scamp_note_list,_,solkattu_list = cparser.parse_notation_file(notation_file)
    _write_to_midi_and_play(scamp_note_list,include_percussion_layer=include_percussion_layer,solkattu_list=solkattu_list)
    #print(scamp_note_list)
def play_solkattu_from_file(solkattu_file_name):
    scamp_note_list,_= cparser.parse_solkattu_file(solkattu_file_name)
    _write_to_midi_and_play(scamp_note_list,include_percussion_layer=False)
    #print(scamp_note_list)
if __name__ == '__main__':
    #"""
    settings._PLAYER_TYPE = settings.PLAYER_TYPE.SF2_LOADER
    settings.TEMPO = 72
    thaaLa_index = 4
    settings.THAALA_INDEX = thaaLa_index
    jaathi_index = 2
    settings.JAATHI_INDEX = jaathi_index
    nadai_index = 3
    settings.NADAI_INDEX = nadai_index
    print('thaala',settings.THAALA_NAMES(thaaLa_index).name)
    print('jaathi',settings.JAATHI_NAMES(jaathi_index).name)
    print('thaala',settings.NADAI_NAMES(nadai_index).name)
    print('thaala positions',thaaLa.get_thaaLa_positions(thaaLa_index, jaathi_index))
    tac = thaaLa.total_akshara_count(thaaLa_index, jaathi_index, nadai_index)
    print('total_akshara_count',tac)
    #lesson_file = "Notes/PancharathnaKrithi-jagadhaandhakaaraka.cmn"
    lesson_file = "../test_notes.inp"
    print(settings._INSTRUMENT_VOLUME_LEVELS)
    play_notes_from_file(lesson_file, include_percussion_layer=True)
    exit()
