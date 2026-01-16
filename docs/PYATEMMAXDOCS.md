
   
Docs - Methods - Set
The set methods allow changing switcher settings.

List of set methods
setAudioLevelsEnable
setAudioLevelsEnable(enable:bool) -> None
Set Audio Levels Enable

    Args:
        enable (bool): On/Off
setAudioMixerInputBalance
setAudioMixerInputBalance(audioSource:ATEMConstant, balance:float) -> None
Set Audio Mixer Input Balance

    Args:
        audioSource: see ATEMAudioSources
        balance (float): -1.0-1.0: Left/Right Extremes
setAudioMixerInputMixOption
setAudioMixerInputMixOption(audioSource:ATEMConstant, mixOption:ATEMConstant) -> None
Set Audio Mixer Input Mix Option

    Args:
        audioSource: see ATEMAudioSources
        mixOption: see ATEMAudioMixerInputMixOptions
setAudioMixerInputVolume
setAudioMixerInputVolume(audioSource:ATEMConstant, db:float) -> None
Set Audio Mixer Input Volume

    Args:
        audioSource: see ATEMAudioSources
        db (float): volume in dB
setAudioMixerMasterVolume
setAudioMixerMasterVolume(db:float) -> None
Set Audio Mixer Master Volume

    Args:
        db (float): volume in dB
setAudioMixerMonitorDim
setAudioMixerMonitorDim(dim:bool) -> None
Set Audio Mixer Monitor Dim

    Args:
        dim (bool): On/Off
setAudioMixerMonitorMonitorAudio
setAudioMixerMonitorMonitorAudio(monitorAudio:bool) -> None
Set Audio Mixer Monitor Monitor Audio

    Args:
        monitorAudio (bool): On/Off
setAudioMixerMonitorMute
setAudioMixerMonitorMute(mute:bool) -> None
Set Audio Mixer Monitor Mute

    Args:
        mute (bool): On/Off
setAudioMixerMonitorSolo
setAudioMixerMonitorSolo(solo:bool) -> None
Set Audio Mixer Monitor Solo

    Args:
        solo (bool): On/Off
setAudioMixerMonitorSoloInput
setAudioMixerMonitorSoloInput(soloInput:ATEMConstant) -> None
Set Audio Mixer Monitor Solo Input

    Args:
        soloInput: see ATEMAudioSources
setAudioMixerMonitorVolume
setAudioMixerMonitorVolume(db:float) -> None
Set Audio Mixer Monitor Volume

    Args:
        db (float): volume in dB
setAuxSourceInput
setAuxSourceInput(auxChannel:ATEMConstant, input_:ATEMConstant) -> None
Set Aux Source Input

    Args:
        auxChannel: see ATEMAUXChannels
        input_: see ATEMVideoSources
setCameraControlAutoFocus
setCameraControlAutoFocus(camera:ATEMConstant) -> None
Set Camera Control Auto focus

    Args:
        camera: see ATEMCameras
setCameraControlAutoIris
setCameraControlAutoIris(camera:ATEMConstant) -> None
Set Camera Control Auto iris

    Args:
        camera: see ATEMCameras
setCameraControlColorbars
setCameraControlColorbars(camera:ATEMConstant, colorbars:int) -> None
Set Camera Control Colorbars

    Args:
        camera: see ATEMCameras
        colorbars: duration in secs (0=disable)
setCameraControlComponentGain
setCameraControlComponentGain(camera:ATEMConstant, gainR:float, gainG:float, gainB:float, gainY:float) -> None
Set Camera Control Component Gain

    Args:
        camera: see ATEMCameras
        gainR (float): 0.0-16.0
        gainG (float): 0.0-16.0
        gainB (float): 0.0-16.0
        gainY (float): 0.0-16.0
setCameraControlContrast
setCameraControlContrast(camera:ATEMConstant, contrast:float) -> None
Set Camera Control Contrast

    Args:
        camera: see ATEMCameras
        contrast (float): 0.0-100.0 (%)
setCameraControlFocus
setCameraControlFocus(camera:ATEMConstant, focus:int) -> None
Set Camera Control Focus

    Args:
        camera: see ATEMCameras
        focus (int): 0-65535
setCameraControlGain
setCameraControlGain(camera:ATEMConstant, gain:int) -> None
Set Camera Control Gain

    Args:
        camera: see ATEMCameras
        gain (int): 512: 0db, 1024: 6db, 2048: 12db, 4096: 18db
setCameraControlGainB
setCameraControlGainB(camera:ATEMConstant, gainB:float) -> None
Set Camera Control Gain B

    Args:
        camera: see ATEMCameras
        gainB (float): 0.0-16.0
setCameraControlGainG
setCameraControlGainG(camera:ATEMConstant, gainG:float) -> None
Set Camera Control Gain G

    Args:
        camera: see ATEMCameras
        gainG (float): 0.0-16.0
setCameraControlGainR
setCameraControlGainR(camera:ATEMConstant, gainR:float) -> None
Set Camera Control Gain R

    Args:
        camera: see ATEMCameras
        gainR (float): 0.0-16.0
setCameraControlGainY
setCameraControlGainY(camera:ATEMConstant, gainY:float) -> None
Set Camera Control Gain Y

    Args:
        camera: see ATEMCameras
        gainY (float): 0.0-16.0
setCameraControlGamma
setCameraControlGamma(camera:ATEMConstant, gammaR:float, gammaG:float, gammaB:float, gammaY:float) -> None
Set Camera Control Gamma

    Args:
        camera: see ATEMCameras
        gammaR (float): -1.0-1.0
        gammaG (float): -1.0-1.0
        gammaB (float): -1.0-1.0
        gammaY (float): -1.0-1.0
setCameraControlGammaB
setCameraControlGammaB(camera:ATEMConstant, gammaB:float) -> None
Set Camera Control Gamma B

    Args:
        camera: see ATEMCameras
        gammaB (float): -1.0-1.0
setCameraControlGammaG
setCameraControlGammaG(camera:ATEMConstant, gammaG:float) -> None
Set Camera Control Gamma G

    Args:
        camera: see ATEMCameras
        gammaG (float): -1.0-1.0
setCameraControlGammaR
setCameraControlGammaR(camera:ATEMConstant, gammaR:float) -> None
Set Camera Control Gamma R

    Args:
        camera: see ATEMCameras
        gammaR (float): -1.0-1.0
setCameraControlGammaY
setCameraControlGammaY(camera:ATEMConstant, gammaY:float) -> None
Set Camera Control Gamma Y

    Args:
        camera: see ATEMCameras
        gammaY (float): -1.0-1.0
setCameraControlHue
setCameraControlHue(camera:ATEMConstant, hue:float) -> None
Set Camera Control Hue

    Args:
        camera: see ATEMCameras
        hue (float): 0.0-359.9 degrees
setCameraControlHueSaturation
setCameraControlHueSaturation(camera:ATEMConstant, hue:float, saturation:float) -> None
Set Camera Control Hue/Saturation

    Args:
        camera: see ATEMCameras
        hue (float): 0.0-359.9 degrees
        saturation (float): 0.0-100.0 (%)
setCameraControlIris
setCameraControlIris(camera:ATEMConstant, iris:int) -> None
Set Camera Control Iris

    Args:
        camera: see ATEMCameras
        iris (int): 0-2048
setCameraControlLift
setCameraControlLift(camera:ATEMConstant, liftR:float, liftG:float, liftB:float, liftY:float) -> None
Set Camera Control Lift

    Args:
        camera: see ATEMCameras
        liftR (float): -1.0-1.0
        liftG (float): -1.0-1.0
        liftB (float): -1.0-1.0
        liftY (float): -1.0-1.0
setCameraControlLiftB
setCameraControlLiftB(camera:ATEMConstant, liftB:float) -> None
Set Camera Control Lift B

    Args:
        camera: see ATEMCameras
        liftB (float): -1.0-1.0
setCameraControlLiftG
setCameraControlLiftG(camera:ATEMConstant, liftG:float) -> None
Set Camera Control Lift G

    Args:
        camera: see ATEMCameras
        liftG (float): -1.0-1.0
setCameraControlLiftR
setCameraControlLiftR(camera:ATEMConstant, liftR:float) -> None
Set Camera Control Lift R

    Args:
        camera: see ATEMCameras
        liftR (float): -1.0-1.0
setCameraControlLiftY
setCameraControlLiftY(camera:ATEMConstant, liftY:float) -> None
Set Camera Control Lift Y

    Args:
        camera: see ATEMCameras
        liftY (float): -1.0-1.0
setCameraControlLumMix
setCameraControlLumMix(camera:ATEMConstant, lumMix:float) -> None
Set Camera Control Lum Mix

    Args:
        camera: see ATEMCameras
        lumMix (float):  0.0-100.0 (%)
setCameraControlResetAll
setCameraControlResetAll(camera:ATEMConstant) -> None
Set Camera Control Reset all

    Args:
        camera: see ATEMCameras
setCameraControlSaturation
setCameraControlSaturation(camera:ATEMConstant, saturation:float) -> None
Set Camera Control Saturation

    Args:
        camera: see ATEMCameras
        saturation (float):  0.0-100.0 (%)
setCameraControlSharpeningLevel
setCameraControlSharpeningLevel(camera:ATEMConstant, detail:ATEMConstant) -> None
Set Camera Control Detail level

    Args:
        camera: see ATEMCameras
        detail: see ATEMCamerControlSharpeningLevels
setCameraControlShutter
setCameraControlShutter(camera:ATEMConstant, shutter:float) -> None
Set Camera Control Shutter

    Args:
        camera: see ATEMCameras
        shutter (float): 1/50, 1/60, 1/75, 1/90, 1/100, 1/120, 1/150, 1/180, 1/250, 1/360, 1/500, 1/750, 1/1000, 1/1450, 1/2000
setCameraControlVideomode
setCameraControlVideomode(camera:ATEMConstant, fps:int, resolution:int, interlaced:int) -> None
Set Camera Control Video Mode

    Args:
        camera: see ATEMCameras
        fps (int): ?
        resolution (int): ?
        interlaced (int): ?
setCameraControlWhiteBalance
setCameraControlWhiteBalance(camera:ATEMConstant, whiteBalance:int) -> None
Set Camera Control White Balance

    Args:
        camera: see ATEMCameras
        whiteBalance(int): 3200: 3200K, 4500: 4500K, 5000: 5000K, 5600: 5600K, 6500: 6500K, 7500: 7500K
setCameraControlZoomNormalized
setCameraControlZoomNormalized(camera:ATEMConstant, zoomNormalized:float) -> None
Set Camera Control Zoom Normalized

    Args:
        camera: see ATEMCameras
        zoomNormalized (float): ?
setCameraControlZoomSpeed
setCameraControlZoomSpeed(camera:ATEMConstant, zoomSpeed:float) -> None
Set Camera Control Zoom

    Args:
        camera: see ATEMCameras
        zoomSpeed (float): -1.0-1.0
setClipPlayerAtBeginning
setClipPlayerAtBeginning(mediaPlayer:ATEMConstant, atBeginning:bool) -> None
Set Clip Player At Beginning

    Args:
        mediaPlayer: see ATEMMediaPlayers
        atBeginning (bool): On/Off
setClipPlayerClipFrame
setClipPlayerClipFrame(mediaPlayer:ATEMConstant, clipFrame:int) -> None
Set Clip Player Clip Frame

    Args:
        mediaPlayer: see ATEMMediaPlayers
        clipFrame (int): frame
setClipPlayerLoop
setClipPlayerLoop(mediaPlayer:ATEMConstant, loop:bool) -> None
Set Clip Player Loop

    Args:
        mediaPlayer: see ATEMMediaPlayers
        loop (bool): On/Off
setClipPlayerPlaying
setClipPlayerPlaying(mediaPlayer:ATEMConstant, playing:bool) -> None
Set Clip Player Playing

    Args:
        mediaPlayer: see ATEMMediaPlayers
        playing (bool): On/Off
setColorGeneratorHue
setColorGeneratorHue(colorGenerator:ATEMConstant, hue:float) -> None
Set Color Generator Hue

    Args:
        colorGenerator: see ATEMColorGenerators
        hue (float): 0.0-359.9 (degrees)
setColorGeneratorLuma
setColorGeneratorLuma(colorGenerator:ATEMConstant, luma:float) -> None
Set Color Generator Luma

    Args:
        colorGenerator: see ATEMColorGenerators
        luma (float): 0.0-100.0 (%)
setColorGeneratorSaturation
setColorGeneratorSaturation(colorGenerator:ATEMConstant, saturation:float) -> None
Set Color Generator Saturation

    Args:
        colorGenerator: see ATEMColorGenerators
        saturation (float): 0.0-100.0 (%)
setDownConverterMode
setDownConverterMode(mode:ATEMConstant) -> None
Set Down Converter Mode

    Args:
        mode: see ATEMDownConverterModes
setDownstreamKeyerBottom
setDownstreamKeyerBottom(keyer:ATEMConstant, bottom:float) -> None
Set Downstream Keyer Bottom

    Args:
        keyer: see ATEMKeyers
        bottom (float): -9.0-9.0
setDownstreamKeyerClip
setDownstreamKeyerClip(keyer:ATEMConstant, clip:float) -> None
Set Downstream Keyer Clip

    Args:
        keyer: see ATEMKeyersr 1-4
        clip (float): 0.0-100.0 (%)
setDownstreamKeyerFillSource
setDownstreamKeyerFillSource(keyer:ATEMConstant, fillSource:ATEMConstant) -> None
Set Downstream Keyer Fill Source

    Args:
        keyer: see ATEMKeyers
        fillSource: see ATEMVideoSources
setDownstreamKeyerGain
setDownstreamKeyerGain(keyer:ATEMConstant, gain:float) -> None
Set Downstream Keyer Gain

    Args:
        keyer: see ATEMKeyersr 1-4
        gain (float): 0.0-100.0 (%)
setDownstreamKeyerInvertKey
setDownstreamKeyerInvertKey(keyer:ATEMConstant, invertKey:bool) -> None
Set Downstream Keyer Invert Key(??)

    Args:
        keyer: see ATEMKeyers
        invertKey (bool): On/Off
setDownstreamKeyerKeySource
setDownstreamKeyerKeySource(keyer:ATEMConstant, keySource:ATEMConstant) -> None
Set Downstream Keyer Source

    Args:
        keyer: see ATEMKeyers
        keySource: see ATEMVideoSources
setDownstreamKeyerLeft
setDownstreamKeyerLeft(keyer:ATEMConstant, left:float) -> None
Set Downstream Keyer Left

    Args:
        keyer: see ATEMKeyers
        left (float): -9.0-9.0
setDownstreamKeyerMasked
setDownstreamKeyerMasked(keyer:ATEMConstant, masked:bool) -> None
Set Downstream Keyer Masked

    Args:
        keyer: see ATEMKeyers 1-4
        masked (bool): On/Off
setDownstreamKeyerOnAir
setDownstreamKeyerOnAir(keyer:ATEMConstant, onAir:bool) -> None
Set Downstream Keyer On Air

    Args:
        keyer: see ATEMKeyers
        onAir (bool): On/Off
setDownstreamKeyerPreMultiplied
setDownstreamKeyerPreMultiplied(keyer:ATEMConstant, preMultiplied:bool) -> None
Set Downstream Keyer Pre Multiplied

    Args:
        keyer: see ATEMKeyers
        preMultiplied (bool): On/Off
setDownstreamKeyerRate
setDownstreamKeyerRate(keyer:ATEMConstant, rate:int) -> None
Set Downstream Keyer Rate

    Args:
        keyer: see ATEMKeyers
    rate (int): 1-250 (frames)
setDownstreamKeyerRight
setDownstreamKeyerRight(keyer:ATEMConstant, right:float) -> None
Set Downstream Keyer Right

    Args:
        keyer: see ATEMKeyers
        right (float): -9.0-9.0
setDownstreamKeyerTie
setDownstreamKeyerTie(keyer:ATEMConstant, tie:bool) -> None
Set Downstream Keyer Tie

    Args:
        keyer: see ATEMKeyers
        tie (bool): On/Off
setDownstreamKeyerTop
setDownstreamKeyerTop(keyer:ATEMConstant, top:float) -> None
Set Downstream Keyer Top

    Args:
        keyer: see ATEMKeyers
        top (float): -9.0-9.0
setFadeToBlackRate
setFadeToBlackRate(mE:ATEMConstant, rate:int) -> None
Set Fade-To-Black Rate

    Args:
        mE: see ATEMMixEffects
        rate (int): 1-250 (frames)
setInputExternalPortType
setInputExternalPortType(videoSource:ATEMConstant, externalPortType:ATEMConstant) -> None
Set Input Properties External Port Type

    Args:
        videoSource: see ATEMVideoSources
        externalPortType: see ATEMExternalPortTypes
setInputLongName
setInputLongName(videoSource:ATEMConstant, longName:str) -> None
Set Input Properties Long Name

    Args:
        videoSource: see ATEMVideoSources
        longName(str): long name
setInputShortName
setInputShortName(videoSource:ATEMConstant, shortName:str) -> None
Set Input Properties Short Name

    Args:
        videoSource: see ATEMVideoSources
        shortName(str): short name
setKeyChromaGain
setKeyChromaGain(mE:ATEMConstant, keyer:ATEMConstant, gain:float) -> None
Set Key Chroma Gain

    Args:
        mE: see ATEMMixEffects
        keyer: see ATEMKeyers
        gain (float): 0.0-100.0 (%)
setKeyChromaHue
setKeyChromaHue(mE:ATEMConstant, keyer:ATEMConstant, hue:float) -> None
Set Key Chroma Hue

    Args:
        mE: see ATEMMixEffects
        keyer: see ATEMKeyers
        hue (float): 0.0-359.9 (degrees)
setKeyChromaLift
setKeyChromaLift(mE:ATEMConstant, keyer:ATEMConstant, lift:float) -> None
Set Key Chroma Lift

    Args:
        mE: see ATEMMixEffects
        keyer: see ATEMKeyers
        lift (float): 0.0-100.0 (%)
setKeyChromaNarrow
setKeyChromaNarrow(mE:ATEMConstant, keyer:ATEMConstant, narrow:bool) -> None
Set Key Chroma Narrow

    Args:
        mE: see ATEMMixEffects
        keyer: see ATEMKeyers
        narrow (bool): On/Off
setKeyChromaYSuppress
setKeyChromaYSuppress(mE:ATEMConstant, keyer:ATEMConstant, ySuppress:float) -> None
Set Key Chroma Y Suppress

    Args:
        mE: see ATEMMixEffects
        keyer: see ATEMKeyers
        ySuppress (float): 0.0-100.0 (%)
setKeyDVEBorderBevel
setKeyDVEBorderBevel(mE:ATEMConstant, keyer:ATEMConstant, borderBevel:ATEMConstant) -> None
Set Key DVE Border Bevel

    Args:
        mE: see ATEMMixEffects
        keyer: see ATEMKeyers
        borderBevel: see ATEMBorderBevels
setKeyDVEBorderBevelPosition
setKeyDVEBorderBevelPosition(mE:ATEMConstant, keyer:ATEMConstant, borderBevelPosition:float) -> None
Set Key DVE Border Bevel Position

    Args:
        mE: see ATEMMixEffects
        keyer: see ATEMKeyers
        borderBevelPosition (float): 0.0-1.0
setKeyDVEBorderBevelSoftness
setKeyDVEBorderBevelSoftness(mE:ATEMConstant, keyer:ATEMConstant, borderBevelSoftness:float) -> None
Set Key DVE Border Bevel Softness

    Args:
        mE: see ATEMMixEffects
        keyer: see ATEMKeyers
        borderBevelSoftness (float): 0.0-1.0
setKeyDVEBorderEnabled
setKeyDVEBorderEnabled(mE:ATEMConstant, keyer:ATEMConstant, borderEnabled:bool) -> None
Set Key DVE Border Enabled

    Args:
        mE: see ATEMMixEffects
        keyer: see ATEMKeyers
        borderEnabled (bool): On/Off
setKeyDVEBorderHue
setKeyDVEBorderHue(mE:ATEMConstant, keyer:ATEMConstant, borderHue:float) -> None
Set Key DVE Border Hue

    Args:
        mE: see ATEMMixEffects
        keyer: see ATEMKeyers
        borderHue (float): 0.0-359.9 (degrees)
setKeyDVEBorderInnerSoftness
setKeyDVEBorderInnerSoftness(mE:ATEMConstant, keyer:ATEMConstant, borderInnerSoftness:int) -> None
Set Key DVE Border Inner Softness

    Args:
        mE: see ATEMMixEffects
        keyer: see ATEMKeyers
        borderInnerSoftness (int): 0-100 (%)
setKeyDVEBorderInnerWidth
setKeyDVEBorderInnerWidth(mE:ATEMConstant, keyer:ATEMConstant, borderInnerWidth:float) -> None
Set Key DVE Border Inner Width

    Args:
        mE: see ATEMMixEffects
        keyer: see ATEMKeyers
        borderInnerWidth (float): 0.0-16.0
setKeyDVEBorderLuma
setKeyDVEBorderLuma(mE:ATEMConstant, keyer:ATEMConstant, borderLuma:float) -> None
Set Key DVE Border Luma

    Args:
        mE: see ATEMMixEffects
        keyer: see ATEMKeyers
        borderLuma (float): 0.0-100.0 (%)
setKeyDVEBorderOpacity
setKeyDVEBorderOpacity(mE:ATEMConstant, keyer:ATEMConstant, borderOpacity:int) -> None
Set Key DVE Border Opacity

    Args:
        mE: see ATEMMixEffects
        keyer: see ATEMKeyers
        borderOpacity (int): 0-100 (%)
setKeyDVEBorderOuterSoftness
setKeyDVEBorderOuterSoftness(mE:ATEMConstant, keyer:ATEMConstant, borderOuterSoftness:int) -> None
Set Key DVE Border Outer Softness

    Args:
        mE: see ATEMMixEffects
        keyer: see ATEMKeyers
        borderOuterSoftness (int): 0-100 (%)
setKeyDVEBorderOuterWidth
setKeyDVEBorderOuterWidth(mE:ATEMConstant, keyer:ATEMConstant, borderOuterWidth:float) -> None
Set Key DVE Border Outer Width

    Args:
        mE: see ATEMMixEffects
        keyer: see ATEMKeyers
        borderOuterWidth (float): 0.0-16.0
setKeyDVEBorderSaturation
setKeyDVEBorderSaturation(mE:ATEMConstant, keyer:ATEMConstant, borderSaturation:float) -> None
Set Key DVE Border Saturation

    Args:
        mE: see ATEMMixEffects
        keyer: see ATEMKeyers
        borderSaturation (float): 0.0-100.0 (%)
setKeyDVEBottom
setKeyDVEBottom(mE:ATEMConstant, keyer:ATEMConstant, bottom:float) -> None
Set Key DVE Bottom

    Args:
        mE: see ATEMMixEffects
        keyer: see ATEMKeyers
        bottom (float): -9.0-9.0
setKeyDVELeft
setKeyDVELeft(mE:ATEMConstant, keyer:ATEMConstant, left:float) -> None
Set Key DVE Left

    Args:
        mE: see ATEMMixEffects
        keyer: see ATEMKeyers
        left (float): -9.0-9.0
setKeyDVELightSourceAltitude
setKeyDVELightSourceAltitude(mE:ATEMConstant, keyer:ATEMConstant, lightSourceAltitude:int) -> None
Set Key DVE Light Source Altitude

    Args:
        mE: see ATEMMixEffects
        keyer: see ATEMKeyers
        lightSourceAltitude (int): 10-100
setKeyDVELightSourceDirection
setKeyDVELightSourceDirection(mE:ATEMConstant, keyer:ATEMConstant, lightSourceDirection:float) -> None
Set Key DVE Light Source Direction

    Args:
        mE: see ATEMMixEffects
        keyer: see ATEMKeyers
        lightSourceDirection (float): 0.0-359.9 (degrees)
setKeyDVEMasked
setKeyDVEMasked(mE:ATEMConstant, keyer:ATEMConstant, masked:bool) -> None
Set Key DVE Masked

    Args:
        mE: see ATEMMixEffects
        keyer: see ATEMKeyers
        masked (bool): On/Off
setKeyDVEPositionX
setKeyDVEPositionX(mE:ATEMConstant, keyer:ATEMConstant, positionX:float) -> None
Set Key DVE Position X

    Args:
        mE: see ATEMMixEffects
        keyer: see ATEMKeyers
        positionX (float): 0.0-1.0
setKeyDVEPositionY
setKeyDVEPositionY(mE:ATEMConstant, keyer:ATEMConstant, positionY:float) -> None
Set Key DVE Position Y

    Args:
        mE: see ATEMMixEffects
        keyer: see ATEMKeyers
        positionY (float): 0.0-1.0
setKeyDVERate
setKeyDVERate(mE:ATEMConstant, keyer:ATEMConstant, rate:int) -> None
Set Key DVE Rate

    Args:
        mE: see ATEMMixEffects
        keyer: see ATEMKeyers-4
        rate (int): 1-250 (frames)
setKeyDVERight
setKeyDVERight(mE:ATEMConstant, keyer:ATEMConstant, right:float) -> None
Set Key DVE Right

    Args:
        mE: see ATEMMixEffects
        keyer: see ATEMKeyers
        right (float): -9.0-9.0
setKeyDVERotation
setKeyDVERotation(mE:ATEMConstant, keyer:ATEMConstant, rotation:float) -> None
Set Key DVE Rotation

    Args:
        mE: see ATEMMixEffects
        keyer: see ATEMKeyers
        rotation (float): 0.0-359.9 (degrees)
setKeyDVEShadow
setKeyDVEShadow(mE:ATEMConstant, keyer:ATEMConstant, shadow:bool) -> None
Set Key DVE Shadow

    Args:
        mE: see ATEMMixEffects
        keyer: see ATEMKeyers
        shadow (bool): On/Off
setKeyDVESizeX
setKeyDVESizeX(mE:ATEMConstant, keyer:ATEMConstant, sizeX:float) -> None
Set Key DVE Size X

    Args:
        mE: see ATEMMixEffects
        keyer: see ATEMKeyers
        sizeX (float): 0.0-1.0
setKeyDVESizeY
setKeyDVESizeY(mE:ATEMConstant, keyer:ATEMConstant, sizeY:float) -> None
Set Key DVE Size Y

    Args:
        mE: see ATEMMixEffects
        keyer: see ATEMKeyers
        sizeY (float): 0.0-1.0
setKeyDVETop
setKeyDVETop(mE:ATEMConstant, keyer:ATEMConstant, top:float) -> None
Set Key DVE Top

    Args:
        mE: see ATEMMixEffects
        keyer: see ATEMKeyers
        top (float): -9.0-9.0
setKeyLumaClip
setKeyLumaClip(mE:ATEMConstant, keyer:ATEMConstant, clip:float) -> None
Set Key Luma Clip

    Args:
        mE: see ATEMMixEffects
        keyer: see ATEMKeyers
        clip (float): 0.0-100.0 (%)
setKeyLumaGain
setKeyLumaGain(mE:ATEMConstant, keyer:ATEMConstant, gain:float) -> None
Set Key Luma Gain

    Args:
        mE: see ATEMMixEffects
        keyer: see ATEMKeyers
        gain (float): 0.0-100.0 (%)
setKeyLumaInvertKey
setKeyLumaInvertKey(mE:ATEMConstant, keyer:ATEMConstant, invertKey:bool) -> None
Set Key Luma Invert Key

    Args:
        mE: see ATEMMixEffects
        keyer: see ATEMKeyers
        invertKey (bool): On/Off
setKeyLumaPreMultiplied
setKeyLumaPreMultiplied(mE:ATEMConstant, keyer:ATEMConstant, preMultiplied:bool) -> None
Set Key Luma Pre Multiplied

    Args:
        mE: see ATEMMixEffects
        keyer: see ATEMKeyers
        preMultiplied (bool): On/Off
setKeyPatternInvertPattern
setKeyPatternInvertPattern(mE:ATEMConstant, keyer:ATEMConstant, invertPattern:bool) -> None
Set Key Pattern Invert Pattern

    Args:
        mE: see ATEMMixEffects
        keyer: see ATEMKeyers
        invertPattern (bool): On/Off
setKeyPatternPattern
setKeyPatternPattern(mE:ATEMConstant, keyer:ATEMConstant, pattern:ATEMConstant) -> None
Set Key Pattern Pattern

    Args:
        mE: see ATEMMixEffects
        keyer: see ATEMKeyers
        pattern: see ATEMPatternStyles
setKeyPatternPositionX
setKeyPatternPositionX(mE:ATEMConstant, keyer:ATEMConstant, positionX:float) -> None
Set Key Pattern Position X

    Args:
        mE: see ATEMMixEffects
        keyer: see ATEMKeyers
        positionX (float): 0.0-1.0
setKeyPatternPositionY
setKeyPatternPositionY(mE:ATEMConstant, keyer:ATEMConstant, positionY:float) -> None
Set Key Pattern Position Y

    Args:
        mE: see ATEMMixEffects
        keyer: see ATEMKeyers
        positionY (float): 0.0-1.0
setKeyPatternSize
setKeyPatternSize(mE:ATEMConstant, keyer:ATEMConstant, size:float) -> None
Set Key Pattern Size

    Args:
        mE: see ATEMMixEffects
        keyer: see ATEMKeyers
        size (float): 0.0-100.0 (%)
setKeyPatternSoftness
setKeyPatternSoftness(mE:ATEMConstant, keyer:ATEMConstant, softness:float) -> None
Set Key Pattern Softness

    Args:
        mE: see ATEMMixEffects
        keyer: see ATEMKeyers
        softness (float): 0.0-100.0 (%)
setKeyPatternSymmetry
setKeyPatternSymmetry(mE:ATEMConstant, keyer:ATEMConstant, symmetry:float) -> None
Set Key Pattern Symmetry

    Args:
        mE: see ATEMMixEffects
        keyer: see ATEMKeyers
        symmetry (float): 0.0-100.0 (%)
setKeyerBottom
setKeyerBottom(mE:ATEMConstant, keyer:ATEMConstant, bottom:float) -> None
Set Key Mask Bottom

    Args:
        mE: see ATEMMixEffects
        keyer: see ATEMKeyers
        bottom (float): -9.0-9.0
setKeyerFillSource
setKeyerFillSource(mE:ATEMConstant, keyer:ATEMConstant, fillSource:ATEMConstant) -> None
Set Key Fill Fill Source

    Args:
        mE: see ATEMMixEffects
        keyer: see ATEMKeyers
        fillSource: see ATEMVideoSources
setKeyerFlyEnabled
setKeyerFlyEnabled(mE:ATEMConstant, keyer:ATEMConstant, flyEnabled:bool) -> None
Set Key Type Fly Enabled

    Args:
        mE: see ATEMMixEffects
        keyer: see ATEMKeyers
        flyEnabled (bool): On/Off
setKeyerFlyKeyFrame
setKeyerFlyKeyFrame(mE:ATEMConstant, keyer:ATEMConstant, keyFrame:ATEMConstant) -> None
Set Keyer Fly Key Frame

    Args:
        mE: see ATEMMixEffects
        keyer: see ATEMKeyers
        keyFrame: see ATEMKeyFrames
setKeyerKeySource
setKeyerKeySource(mE:ATEMConstant, keyer:ATEMConstant, keySource:ATEMConstant) -> None
Set Key Cut Key Source

    Args:
        mE: see ATEMMixEffects
        keyer: see ATEMKeyers
        keySource: see ATEMVideoSources
setKeyerLeft
setKeyerLeft(mE:ATEMConstant, keyer:ATEMConstant, left:float) -> None
Set Key Mask Left

    Args:
        mE: see ATEMMixEffects
        keyer: see ATEMKeyers
        left (float): -9.0-9.0
setKeyerMasked
setKeyerMasked(mE:ATEMConstant, keyer:ATEMConstant, masked:bool) -> None
Set Key Mask Masked

    Args:
        mE: see ATEMMixEffects
        keyer: see ATEMKeyers
        masked (bool): On/Off
setKeyerOnAirEnabled
setKeyerOnAirEnabled(mE:ATEMConstant, keyer:ATEMConstant, enabled:bool) -> None
Set Keyer On Air Enabled

    Args:
        mE: see ATEMMixEffects
        keyer: see ATEMKeyers
        enabled (bool): On/Off
setKeyerRight
setKeyerRight(mE:ATEMConstant, keyer:ATEMConstant, right:float) -> None
Set Key Mask Right

    Args:
        mE: see ATEMMixEffects
        keyer: see ATEMKeyers
        right (float): -9.0-9.0
setKeyerTop
setKeyerTop(mE:ATEMConstant, keyer:ATEMConstant, top:float) -> None
Set Key Mask Top

    Args:
        mE: see ATEMMixEffects
        keyer: see ATEMKeyers
        top (float): -9.0-9.0
setKeyerType
setKeyerType(mE:ATEMConstant, keyer:ATEMConstant, type_:ATEMConstant) -> None
Set Key Type Type

    Args:
        mE: see ATEMMixEffects
        keyer: see ATEMKeyers
        type_: see ATEMKeyerTypes
setMacroAction
setMacroAction(macro:ATEMConstant, action:ATEMConstant) -> None
Set Macro Action Action

    Args:
        macro: see ATEMMacros (to stop, use macros.stop)
        action: see ATEMMacroActions
setMacroAddPauseFrames
setMacroAddPauseFrames(frames:int) -> None
Set Macro Add Pause Frames

    Args:
        frames (int): number of frames
setMacroRunChangePropertiesLooping
setMacroRunChangePropertiesLooping(looping:bool) -> None
Set Macro Run Change Properties Looping

    Args:
        looping (bool): On/Off
setMediaPlayerSourceClipIndex
setMediaPlayerSourceClipIndex(mediaPlayer:ATEMConstant, clipIndex:int) -> None
Set Media Player Source Clip Index

    Args:
        mediaPlayer: see ATEMMediaPlayers
        clipIndex (int): 0-x: Clip 1-x
setMediaPlayerSourceStillIndex
setMediaPlayerSourceStillIndex(mediaPlayer:ATEMConstant, stillIndex:int) -> None
Set Media Player Source Still Index

    Args:
        mediaPlayer: see ATEMMediaPlayers
        stillIndex (int): 0-x: Still 1-x
setMediaPlayerSourceType
setMediaPlayerSourceType(mediaPlayer:ATEMConstant, type_:ATEMConstant) -> None
Set Media Player Source Type

    Args:
        mediaPlayer: see ATEMMediaPlayers
        type_: see ATEMMediaPlayerSourceTypes
setMediaPoolStorageClip1MaxLength
setMediaPoolStorageClip1MaxLength(clip1MaxLength:int) -> None
Set Media Pool Storage Clip 1 Max Length

    Args:
        clip1MaxLength (int): frames
setMultiViewerInputVideoSource
setMultiViewerInputVideoSource(multiViewer:ATEMConstant, window:ATEMConstant, videoSource:ATEMConstant) -> None
Set MultiViewer Properties Video Source

    Args:
        multiViewer: see ATEMMultiViewers
        window: see ATEMWindows
        videoSource: see ATEMVideoSources
setMultiViewerPropertiesLayout
setMultiViewerPropertiesLayout(multiViewer:ATEMConstant, layout:ATEMConstant) -> None
Set MultiViewer Properties Layout

    Args:
        videoSource: see ATEMVideoSources
        layout: see ATEMMultiViewerLayouts
setPreviewInputVideoSource
setPreviewInputVideoSource(mE:ATEMConstant, videoSource:ATEMConstant) -> None
Set Preview Input Video Source

    Args:
        mE: see ATEMMixEffects
        videoSource: see ATEMVideoSources
setProgramInputVideoSource
setProgramInputVideoSource(mE:ATEMConstant, videoSource:ATEMConstant) -> None
Set Program Input Video Source

    Args:
        mE: see ATEMMixEffects
        videoSource: see ATEMVideoSources
setResetAudioMixerPeaksInputSource
setResetAudioMixerPeaksInputSource(inputSource:ATEMConstant) -> None
Set Reset Audio Mixer Peaks Input Source

    Args:
        inputSource: see ATEMAudioSources
setResetAudioMixerPeaksMaster
setResetAudioMixerPeaksMaster(master:bool) -> None
Set Reset Audio Mixer Peaks Master

    Args:
        master (bool): Yes/No
setRunFlyingKeyKeyFrame
setRunFlyingKeyKeyFrame(mE:ATEMConstant, keyer:ATEMConstant, keyFrame:ATEMConstant) -> None
Set Run Flying Key Key Frame

    Args:
        mE: see ATEMMixEffects
        keyer: see ATEMKeyers
        keyFrame: see ATEMKeyFrames
setRunFlyingKeyRuntoInfiniteindex
setRunFlyingKeyRuntoInfiniteindex(mE:ATEMConstant, keyer:ATEMConstant, runtoInfiniteindex:int) -> None
Set Run Flying Key Run-to-Infinite-index

    Args:
        mE: see ATEMMixEffects
        keyer: see ATEMKeyerser 1-4
        runtoInfiniteindex (int): index
setSuperSourceBorderBevel
setSuperSourceBorderBevel(borderBevel:ATEMConstant) -> None
Set Super Source Border Bevel

    Args:
        borderBevel: see ATEMBorderBevels
setSuperSourceBorderBevelPosition
setSuperSourceBorderBevelPosition(borderBevelPosition:float) -> None
Set Super Source Border Bevel Position

    Args:
        borderBevelPosition (float): 0.0-1.0
setSuperSourceBorderBevelSoftness
setSuperSourceBorderBevelSoftness(borderBevelSoftness:float) -> None
Set Super Source Border Bevel Softness

    Args:
        borderBevelSoftness (float): 0.0-1.0
setSuperSourceBorderEnabled
setSuperSourceBorderEnabled(borderEnabled:bool) -> None
Set Super Source Border Enabled

    Args:
        borderEnabled (bool): On/Off
setSuperSourceBorderHue
setSuperSourceBorderHue(borderHue:float) -> None
Set Super Source Border Hue

    Args:
        borderHue (float): 0.0-359.9 (degrees)
setSuperSourceBorderInnerSoftness
setSuperSourceBorderInnerSoftness(borderInnerSoftness:int) -> None
Set Super Source Border Inner Softness

    Args:
        borderInnerSoftness (int): 0-100 (%)
setSuperSourceBorderInnerWidth
setSuperSourceBorderInnerWidth(borderInnerWidth:float) -> None
Set Super Source Border Inner Width

    Args:
        borderInnerWidth (float): 0.0-16.0
setSuperSourceBorderLuma
setSuperSourceBorderLuma(borderLuma:float) -> None
Set Super Source Border Luma

    Args:
        borderLuma (float): 0.0-100.0 (%)
setSuperSourceBorderOuterSoftness
setSuperSourceBorderOuterSoftness(borderOuterSoftness:int) -> None
Set Super Source Border Outer Softness

    Args:
        borderOuterSoftness (int): 0-100 (%)
setSuperSourceBorderOuterWidth
setSuperSourceBorderOuterWidth(borderOuterWidth:float) -> None
Set Super Source Border Outer Width

    Args:
        borderOuterWidth (float): 0.0-16.0
setSuperSourceBorderSaturation
setSuperSourceBorderSaturation(borderSaturation:float) -> None
Set Super Source Border Saturation

    Args:
        borderSaturation (float): 0.0-100.0 (%)
setSuperSourceBoxParametersCropBottom
setSuperSourceBoxParametersCropBottom(box:ATEMConstant, cropBottom:float) -> None
Set Super Source Box Parameters Crop Bottom

    Args:
        box: see ATEMBoxes
        cropBottom (float): 0.0-18.0
setSuperSourceBoxParametersCropLeft
setSuperSourceBoxParametersCropLeft(box:ATEMConstant, cropLeft:float) -> None
Set Super Source Box Parameters Crop Left

    Args:
        box: see ATEMBoxes
        cropLeft (float): 0.0-32.0
setSuperSourceBoxParametersCropRight
setSuperSourceBoxParametersCropRight(box:ATEMConstant, cropRight:float) -> None
Set Super Source Box Parameters Crop Right

    Args:
        box: see ATEMBoxes
        cropRight (float): 0.0-32.0
setSuperSourceBoxParametersCropTop
setSuperSourceBoxParametersCropTop(box:ATEMConstant, cropTop:float) -> None
Set Super Source Box Parameters Crop Top

    Args:
        box: see ATEMBoxes
        cropTop (float): 0.0-18.0
setSuperSourceBoxParametersCropped
setSuperSourceBoxParametersCropped(box:ATEMConstant, cropped:bool) -> None
Set Super Source Box Parameters Cropped

    Args:
        box: see ATEMBoxes
        cropped (bool): On/Off
setSuperSourceBoxParametersEnabled
setSuperSourceBoxParametersEnabled(box:ATEMConstant, enabled:bool) -> None
Set Super Source Box Parameters Enabled

    Args:
        box: see ATEMBoxes
        enabled (bool): On/Off
setSuperSourceBoxParametersInputSource
setSuperSourceBoxParametersInputSource(box:ATEMConstant, inputSource:ATEMConstant) -> None
Set Super Source Box Parameters Input Source

    Args:
        box: see ATEMBoxes
        inputSource: see ATEMVideoSources
setSuperSourceBoxParametersPositionX
setSuperSourceBoxParametersPositionX(box:ATEMConstant, positionX:float) -> None
Set Super Source Box Parameters Position X

    Args:
        box: see ATEMBoxes
        positionX (float): -48.0-48.0
setSuperSourceBoxParametersPositionY
setSuperSourceBoxParametersPositionY(box:ATEMConstant, positionY:float) -> None
Set Super Source Box Parameters Position Y

    Args:
        box: see ATEMBoxes
        positionY (float): -27.0-27.0
setSuperSourceBoxParametersSize
setSuperSourceBoxParametersSize(box:ATEMConstant, size:float) -> None
Set Super Source Box Parameters Size

    Args:
        box: see ATEMBoxes
        size (float): 0.07-1.0
setSuperSourceClip
setSuperSourceClip(clip:float) -> None
Set Super Source Clip

    Args:
        clip (float): 0.0-100.0 (%)
setSuperSourceFillSource
setSuperSourceFillSource(fillSource:ATEMConstant) -> None
Set Super Source Fill Source

    Args:
        fillSource: see ATEMVideoSources
setSuperSourceForeground
setSuperSourceForeground(foreground:bool) -> None
Set Super Source Foreground

    Args:
        foreground (bool): On/Off
setSuperSourceGain
setSuperSourceGain(gain:float) -> None
Set Super Source Gain

    Args:
        gain (float): 0.0-100.0 (%)
setSuperSourceInvertKey
setSuperSourceInvertKey(invertKey:bool) -> None
Set Super Source Invert Key

    Args:
        invertKey (bool): On/Off
setSuperSourceKeySource
setSuperSourceKeySource(keySource:ATEMConstant) -> None
Set Super Source Key Source

    Args:
        keySource: see ATEMVideoSources
setSuperSourceLightSourceAltitude
setSuperSourceLightSourceAltitude(lightSourceAltitude:int) -> None
Set Super Source Light Source Altitude

    Args:
        lightSourceAltitude (int): 10-100
setSuperSourceLightSourceDirection
setSuperSourceLightSourceDirection(lightSourceDirection:float) -> None
Set Super Source Light Source Direction

    Args:
        lightSourceDirection (float): 0.0-359.9 (degrees)
setSuperSourcePreMultiplied
setSuperSourcePreMultiplied(preMultiplied:bool) -> None
Set Super Source Pre Multiplied

    Args:
        preMultiplied (bool): On/Off
setTransitionDVEClip
setTransitionDVEClip(mE:ATEMConstant, clip:float) -> None
Set Transition DVE Clip

    Args:
        mE: see ATEMMixEffects
        clip (float): 0.0-100.0 (%)
setTransitionDVEEnableKey
setTransitionDVEEnableKey(mE:ATEMConstant, enableKey:bool) -> None
Set Transition DVE Enable Key

    Args:
        mE: see ATEMMixEffects
        enableKey (bool): On/Off
setTransitionDVEFillSource
setTransitionDVEFillSource(mE:ATEMConstant, fillSource:ATEMConstant) -> None
Set Transition DVE Fill Source

    Args:
        mE: see ATEMMixEffects
        fillSource: see ATEMVideoSources
setTransitionDVEFlipFlop
setTransitionDVEFlipFlop(mE:ATEMConstant, flipFlop:bool) -> None
Set Transition DVE FlipFlop

    Args:
        mE: see ATEMMixEffects
        flipFlop (bool): On/Off
setTransitionDVEGain
setTransitionDVEGain(mE:ATEMConstant, gain:float) -> None
Set Transition DVE Gain

    Args:
        mE: see ATEMMixEffects
        gain (float): 0.0-100.0 (%)
setTransitionDVEInvertKey
setTransitionDVEInvertKey(mE:ATEMConstant, invertKey:bool) -> None
Set Transition DVE Invert Key

    Args:
        mE: see ATEMMixEffects
        invertKey (bool): On/Off
setTransitionDVEKeySource
setTransitionDVEKeySource(mE:ATEMConstant, keySource:ATEMConstant) -> None
Set Transition DVE Key Source

    Args:
        mE: see ATEMMixEffects
        keySource: see ATEMVideoSources
setTransitionDVEPreMultiplied
setTransitionDVEPreMultiplied(mE:ATEMConstant, preMultiplied:bool) -> None
Set Transition DVE Pre Multiplied

    Args:
        mE: see ATEMMixEffects
        preMultiplied (bool): On/Off
setTransitionDVERate
setTransitionDVERate(mE:ATEMConstant, rate:int) -> None
Set Transition DVE Rate

    Args:
        mE: see ATEMMixEffects
        rate (int): 1-250 (frames)
setTransitionDVEReverse
setTransitionDVEReverse(mE:ATEMConstant, reverse:bool) -> None
Set Transition DVE Reverse

    Args:
        mE: see ATEMMixEffects
        reverse (bool): On/Off
setTransitionDVEStyle
setTransitionDVEStyle(mE:ATEMConstant, style:ATEMConstant) -> None
Set Transition DVE Style

    Args:
        mE: see ATEMMixEffects
        style: see ATEMDVETransitionStyles
setTransitionDipInput
setTransitionDipInput(mE:ATEMConstant, input_:ATEMConstant) -> None
Set Transition Dip Input

    Args:
        mE: see ATEMMixEffects
        input_: see ATEMVideoSources
setTransitionDipRate
setTransitionDipRate(mE:ATEMConstant, rate:int) -> None
Set Transition Dip Rate

    Args:
        mE: see ATEMMixEffects
        rate (int): 1-250 (frames)
setTransitionMixRate
setTransitionMixRate(mE:ATEMConstant, rate:int) -> None
Set Transition Mix Rate

    Args:
        mE: see ATEMMixEffects
        rate (int): 1-250 (frames)
setTransitionNextTransition
setTransitionNextTransition(mE:ATEMConstant, nextTransition:int) -> None
Set Transition Style Next Transition

    Args:
        mE: see ATEMMixEffects
        nextTransition: see ATEMTransitionStyles
setTransitionPosition
setTransitionPosition(mE:ATEMConstant, position:int) -> None
Set Transition Preview Enabled

    Args:
        mE: see ATEMMixEffects
        position (int): 0-9999
setTransitionPreviewEnabled
setTransitionPreviewEnabled(mE:ATEMConstant, enabled:bool) -> None
Set Transition Preview Enabled

    Args:
        mE: see ATEMMixEffects
        enabled (bool): On/Off
setTransitionStingerClip
setTransitionStingerClip(mE:ATEMConstant, clip:float) -> None
Set Transition Stinger Clip

    Args:
        mE: see ATEMMixEffects
        clip (float): 0.0-100.0 (%)
setTransitionStingerClipDuration
setTransitionStingerClipDuration(mE:ATEMConstant, clipDuration:int) -> None
Set Transition Stinger Clip Duration

    Args:
        mE: see ATEMMixEffects
        clipDuration (int): frames
setTransitionStingerGain
setTransitionStingerGain(mE:ATEMConstant, gain:float) -> None
Set Transition Stinger Gain

    Args:
        mE: see ATEMMixEffects
        gain (float): 0.0-100.0 (%)
setTransitionStingerInvertKey
setTransitionStingerInvertKey(mE:ATEMConstant, invertKey:bool) -> None
Set Transition Stinger Invert Key

    Args:
        mE: see ATEMMixEffects
        invertKey (bool): On/Off
setTransitionStingerMixRate
setTransitionStingerMixRate(mE:ATEMConstant, mixRate:int) -> None
Set Transition Stinger Mix Rate

    Args:
        mE: see ATEMMixEffects
        mixRate (int): frames
setTransitionStingerPreMultiplied
setTransitionStingerPreMultiplied(mE:ATEMConstant, preMultiplied:bool) -> None
Set Transition Stinger Pre Multiplied

    Args:
        mE: see ATEMMixEffects
        preMultiplied (bool): On/Off
setTransitionStingerPreRoll
setTransitionStingerPreRoll(mE:ATEMConstant, preRoll:int) -> None
Set Transition Stinger Pre Roll

    Args:
        mE: see ATEMMixEffects
        preRoll (int): frames
setTransitionStingerSource
setTransitionStingerSource(mE:ATEMConstant, source:ATEMConstant) -> None
Set Transition Stinger Source

    Args:
        mE: see ATEMMixEffects
        source: see ATEMMediaPlayers
setTransitionStingerTriggerPoint
setTransitionStingerTriggerPoint(mE:ATEMConstant, triggerPoint:int) -> None
Set Transition Stinger Trigger Point

    Args:
        mE: see ATEMMixEffects
        triggerPoint (int): frames
setTransitionStyle
setTransitionStyle(mE:ATEMConstant, style:ATEMConstant) -> None
Set Transition Style

    Args:
        mE: see ATEMMixEffects
        style: see ATEMTransitionStyles
setTransitionWipeFillSource
setTransitionWipeFillSource(mE:ATEMConstant, fillSource:ATEMConstant) -> None
Set Transition Wipe Fill Source

    Args:
        mE: see ATEMMixEffects
        fillSource: see ATEMVideoSources
setTransitionWipeFlipFlop
setTransitionWipeFlipFlop(mE:ATEMConstant, flipFlop:bool) -> None
Set Transition Wipe FlipFlop

    Args:
        mE: see ATEMMixEffects
        flipFlop (bool): On/Off
setTransitionWipePattern
setTransitionWipePattern(mE:ATEMConstant, pattern:ATEMConstant) -> None
Set Transition Wipe Pattern

    Args:
        mE: see ATEMMixEffects
        pattern: see ATEMPatternStyles
setTransitionWipePositionX
setTransitionWipePositionX(mE:ATEMConstant, positionX:float) -> None
Set Transition Wipe Position X

    Args:
        mE: see ATEMMixEffects
        positionX (float): 0.0-1.0
setTransitionWipePositionY
setTransitionWipePositionY(mE:ATEMConstant, positionY:float) -> None
Set Transition Wipe Position Y

    Args:
        mE: see ATEMMixEffects
        positionY (float): 0.0-1.0
setTransitionWipeRate
setTransitionWipeRate(mE:ATEMConstant, rate:int) -> None
Set Transition Wipe Rate

    Args:
        mE: see ATEMMixEffects
        rate (int): 1-250 (frames)
setTransitionWipeReverse
setTransitionWipeReverse(mE:ATEMConstant, reverse:bool) -> None
Set Transition Wipe Reverse

    Args:
        mE: see ATEMMixEffects
        reverse (bool): On/Off
setTransitionWipeSoftness
setTransitionWipeSoftness(mE:ATEMConstant, softness:float) -> None
Set Transition Wipe Softness

    Args:
        mE: see ATEMMixEffects
        softness (float): 0.0-100.0 (%)
setTransitionWipeSymmetry
setTransitionWipeSymmetry(mE:ATEMConstant, symmetry:float) -> None
Set Transition Wipe Symmetry

    Args:
        mE: see ATEMMixEffects
        symmetry (float): 0.0-100.0 (%)
setTransitionWipeWidth
setTransitionWipeWidth(mE:ATEMConstant, width:float) -> None
Set Transition Wipe Width

    Args:
        mE: see ATEMMixEffects
        width (float): 0.0-100.0 (%)
setVideoModeFormat
setVideoModeFormat(format_:ATEMConstant) -> None
Set Video Mode Format

    Args:
        format_: see ATEMVideoModeFormats
PyATEMMax
Tony Aguilar
onixag@gmail.com
 PyATEMMax
A Python library to monitor and control Blackmagic Design ATEM video switchers.