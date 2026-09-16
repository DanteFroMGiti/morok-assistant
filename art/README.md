# Кадры сидения Морока

`morok-sit-down-source.png`, `morok-sitting-source.png` и
`morok-sitting-watch-source.png` созданы встроенным imagegen
с прозрачным фоном. Для сидения использовался исходный `sprites.png`, для посадки —
исходный атлас и готовые кадры сидения, для взглядов — готовые кадры сидения.
Атлас собирается командой
`python tools/build_sitting_atlas.py`. Новые кадры сна и удержания указателя хранятся
в `morok-curl-sleep-source.png` и `morok-pointer-hold-source.png`; они добавляются в
`sprites-v4.png` командой `python tools/build_behavior_atlas.py`.
Кадры просмотра видео боком хранятся в `morok-video-watching-source.png` и
добавляются в `sprites-v5.png` командой `python tools/build_video_atlas.py`.

Запрос для `morok-video-watching-source.png`:

> Use case: precise-object-edit. Asset type: four-frame transparent sprite strip.
> Transform the sitting Morok into a rear three-quarter seated pose, head turned toward
> the video on his right so one red eye and part of the muzzle remain visible. Preserve
> his charcoal fur, horns, large magenta ears, wings and painterly style. Animate only a
> gentle tail wag across four evenly spaced full-body frames with a shared baseline and
> genuine transparency. No scenery, floor, shadows, text, props or extra limbs.

Запрос для `morok-sitting-source.png`:

> Создать четыре кадра Морока, сидящего на земле и спокойно ожидающего: переход к
> посадке, взгляд с открытыми глазами, полуприкрытые глаза и моргание. Точно сохранить
> персонажа, палитру, рога, крылья, хвост, красные глаза и стиль исходного атласа.
> Разместить кадры рядом с одинаковой линией земли и прозрачным фоном, без реквизита,
> надписей и сетки.

Запрос для `morok-sit-down-source.png`:

> Создать четыре последовательных кадра посадки того же Морока: стоит, сгибает колени,
> опускается и сидит ровно как в готовых кадрах ожидания. Точно сохранить внешность и
> стиль исходного атласа, одинаковую линию земли, прозрачность. Без реквизита,
> декораций, надписей и сетки.

Запрос для `morok-sitting-watch-source.png`:

> Создать четыре кадра Морока в той же сидячей позе с одинаковой линией земли:
> глаза смотрят вправо, вверх, вниз и прямо. Сохранить внешность, размер, фон с
> прозрачностью и стиль готовых сидячих кадров. Менять главным образом направление
> взгляда, без предметов, декораций, надписей и сетки.

Для новых кадров использован встроенный imagegen с готовыми полосами сидения и посадки
как образцами. Запрос для `morok-curl-sleep-source.png`:

> Use case: precise-object-edit. Asset type: 4-frame transparent sprite strip for Morok desktop character. Input image is the character and style reference. Create a new horizontal strip of exactly four distinct full-body poses, each centered in an equal-width cell with the same baseline and clear transparent spacing: (1) Morok seated, starting to tuck his head and paws; (2) curling his body and tail around himself; (3) curled into a compact sleeping ball, eyes closed, horns, ears, small folded wings, and tail visible; (4) same sleeping ball with a subtle breathing variation. Preserve the exact charcoal fur, red eyes when open, dark curved horns, large magenta inner ears, bat wings, tail, painterly dark pixel-art style and anatomy from the reference. The sleeping ball should be much lower and more compact than standing or sitting. Genuine transparent background. No props, text, grid, shadows, extra characters, cropped body parts or duplicate frames.

Запрос для `morok-pointer-hold-source.png`:

> Use case: precise-object-edit. Asset type: 4-frame transparent sprite strip for Morok desktop character. Input image is the character and style reference. Create a new horizontal strip of exactly four distinct full-body frames centered in equal-width cells with identical ground baseline and transparent spacing. Morok stands facing forward and raises his right forepaw (viewer-left side) to reach upward toward and cling to an invisible mouse pointer above that paw. Frame 1 paw reaching, frame 2 paw gripping with curved claws, frame 3 holding while body slightly lifted/tilted, frame 4 subtle bounce while still gripping. The paw should clearly read as gripping something at about horn/ear height, but DO NOT draw a mouse cursor or other object; the application will place its real pointer there. Preserve exact charcoal fur, curved dark horns, large magenta inner ears, red eyes, bat wings, tail, painterly dark pixel-art style, and recognizable identity from reference. Genuine transparent background. No props, text, grid, shadows, extra characters, cropped body parts or repeated frames.
