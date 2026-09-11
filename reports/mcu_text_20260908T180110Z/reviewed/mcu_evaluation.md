# MCU RAG evaluation — corrected

Original run: 2026-09-08T18:02:00.400898+00:00

Verdicts: {'correct': 4, 'partial': 4, 'incorrect': 4, 'abstained': 0, 'uncertain': 0}
Improved verdicts: 6/12
Complete core evidence shown: 7/12

- ndcg_at_10: 0.613167 (mean)
- recall_at_10: 0.791667 (mean)
- recall_at_3: 0.541667 (mean)

Verdict transitions only: incorrect/abstained to partial/correct, or partial to correct. Additional facts within an unchanged partial verdict are not counted.

## Limitations

- Gold annotations are provisional; answer judgments require semantic review.

## mcu-draft-001 — incorrect

On an STM32F103C8, USART1 is clocked and PA12 is configured as an alternate-function output for USART1 RTS, but PA12 stays high. CAN is unused and its clock is disabled. What could cause this, and how can I fix it?

Baseline: incorrect; improved: False
Shown page IDs: [100248, 100256, 60012]

### Saved model answer

The issue might be due to a conflict between the I/O port pin PB12 being used for USART1 RTS and the CAN clock being disabled. According to Page 3 of the STM32F103 Errata sheet, when CAN is used with other peripherals that share pins, conflicts may occur.

To fix this, ensure that the CAN clock is enabled if it's intended to be used. If CAN is not needed, enable the I/O port pin PB12 for USART1 RTS by setting the corresponding bit in the GPIO register. This should resolve the conflict and allow PA12 to function correctly as the alternate-function output for USART1 RTS.

### Assessment

Wrong pin and missing erratum workaround; no core fact is satisfied.

- contradicted: Identifies the CAN/USART1_RTS conflict on PA12. Misidentifies the RTS pin as PB12 and invents a CAN/PB12 conflict rather than the required PA12 mechanism.
- missing: Specifies selecting the unused CAN remap when CAN is unused. Does not select the unused CAN remap; suggests GPIO configuration or enabling CAN.

Citations: {'labels': [3], 'invalid_labels': [], 'resolved_page_ids': [60012], 'note': 'Valid local labels do not establish that the cited page supports the claim.'}

Slot 3 (ES096 p12) describes other conflicts, not the CAN/PA12 issue.

Complete evidence shown: False

### Retrieved pages

- 1. st_stm32f407_refman_rm0090 p248 (ID 100248, score 0.6722553042644069)
- 2. st_stm32f407_refman_rm0090 p256 (ID 100256, score 0.6550655724498353)
- 3. st_stm32f103_errata_es096 p12 (ID 60012, score 0.6505586459174927)
- 4. st_stm32f103_errata_es096 p13 (ID 60013, score 0.6452006265559675)
- 5. st_stm32f407_refman_rm0090 p250 (ID 100250, score 0.643502096166272)
- 6. st_stm32f407_refman_rm0090 p247 (ID 100247, score 0.6374041760113908)
- 7. st_stm32f103_errata_es096 p11 (ID 60011, score 0.6363740380696432)
- 8. st_stm32f407_refman_rm0090 p242 (ID 100242, score 0.6356046845623459)
- 9. st_stm32f103_refman_rm0008 p116 (ID 70116, score 0.6338236867440312)
- 10. st_stm32f407_refman_rm0090 p259 (ID 100259, score 0.6273414212364871)

## mcu-draft-002 — correct

On an STM32F103x8/xB, TIM3 channel 2 on PB5 stays high with TIM3 and I2C1 both clocked and PB5 configured as an alternate-function output. SMBus Alert is unused. Why does this happen, and what use of CH2 does the errata permit in this configuration?

Baseline: incorrect; improved: True
Shown page IDs: [60012, 100850, 80035]

### Saved model answer

[Page 1] When TIM3 and I2C1 are both clocked with PB5 configured as an alternate function output, there is a conflict between the TIM3_CH2 signal and the I2C1 SMBA signal. [Page 1] To avoid this conflict, TIM3_CH2 can only be used in input mode.

### Assessment

Both core facts are satisfied.

- met: Explains the I2C1_SMBA conflict despite unused alert. Identifies TIM3_CH2/I2C1_SMBA conflict in the unused-alert scenario supplied by the question.
- met: Restricts CH2 to input in the stated configuration. Explicitly restricts CH2 to input mode.

Citations: {'labels': [1, 1], 'invalid_labels': [], 'resolved_page_ids': [60012], 'note': 'Valid local labels do not establish that the cited page supports the claim.'}

Both claims cite slot 1, ES096 p12.

Complete evidence shown: True

### Retrieved pages

- 1. st_stm32f103_errata_es096 p12 (ID 60012, score 0.6641940388825321)
- 2. st_stm32f407_refman_rm0090 p850 (ID 100850, score 0.6355146480663505)
- 3. st_stm32f407_datasheet_ds8626 p35 (ID 80035, score 0.635312684884118)
- 4. st_stm32f103_errata_es096 p13 (ID 60013, score 0.634433100260965)
- 5. st_stm32f103_datasheet_ds5319 p18 (ID 50018, score 0.6331752455192736)
- 6. st_stm32f407_datasheet_ds8626 p34 (ID 80034, score 0.6264144196526876)
- 7. st_stm32f407_refman_rm0090 p839 (ID 100839, score 0.6246791138977248)
- 8. st_stm32f407_datasheet_ds8626 p20 (ID 80020, score 0.6178386813235801)
- 9. st_stm32f103_datasheet_ds5319 p33 (ID 50033, score 0.615662438721657)
- 10. st_stm32f407_datasheet_ds8626 p123 (ID 80123, score 0.615569338533964)

## mcu-draft-003 — incorrect

On an STM32F103x8/xB, after updating the independent watchdog settings and immediately entering Stop mode, the next watchdog update hangs and eventually resets the MCU. How can this be prevented?

Baseline: incorrect; improved: False
Shown page IDs: [90009, 100137, 100135]

### Saved model answer

This issue can be prevented by ensuring that the independent watchdog (IWDG) is stopped before entering Stop mode. According to [Page 1, Section 21.3], the IWDG cannot be stopped except by a reset once started. Therefore, it's recommended to disable the IWDG before entering Stop mode.

### Assessment

Recommends disabling IWDG while acknowledging it cannot be stopped once started; does not answer the erratum.

- missing: Waits for RVU and PVU to clear before Stop. Does not wait for RVU/PVU before Stop.
- missing: Explains that entering Stop before the watchdog update completes can leave the flags set and block later updates. Does not explain stuck update flags or blocked later updates.

Citations: {'labels': [1], 'invalid_labels': [], 'resolved_page_ids': [90009], 'note': 'Valid local labels do not establish that the cited page supports the claim.'}

The shown context is STM32F407 material, not the required STM32F103 erratum.

Complete evidence shown: False

### Retrieved pages

- 1. st_stm32f407_errata_es0182 p9 (ID 90009, score 0.6706743847350066)
- 2. st_stm32f407_refman_rm0090 p137 (ID 100137, score 0.6495963094757238)
- 3. st_stm32f407_refman_rm0090 p135 (ID 100135, score 0.6454247213140397)
- 4. st_stm32f103_errata_es096 p8 (ID 60008, score 0.6417292997577477)
- 5. st_stm32f407_refman_rm0090 p133 (ID 100133, score 0.6383234915811384)
- 6. st_stm32f407_refman_rm0090 p131 (ID 100131, score 0.63748770838095)
- 7. st_stm32f103_refman_rm0008 p75 (ID 70075, score 0.6370806769702136)
- 8. st_stm32f103_datasheet_ds5319 p16 (ID 50016, score 0.6370565652485384)
- 9. espressif_esp32_errata p20 (ID 20020, score 0.6346182869609419)
- 10. st_stm32f407_refman_rm0090 p134 (ID 100134, score 0.6333870030674011)

## mcu-draft-004 — incorrect

On an STM32F103x8/xB, can clearing a DMA channel's global interrupt flag while the channel is active cause a transfer error to be missed or prevent automatic channel disable? How should software avoid this?

Baseline: partial; improved: False
Shown page IDs: [70285, 100325, 100326]

### Saved model answer

On an STM32F103x8/xB, clearing a DMA channel's global interrupt flag (CGIFx) while the channel is active does not directly cause a transfer error to be missed or prevent automatic channel disable. However, it might affect the handling of interrupts if the corresponding interrupt enable bit is set.

To avoid missing a transfer error or preventing automatic channel disable, software should:
- Clear the CGIFx flag before setting the corresponding interrupt enable bit to '1'.
- Ensure that the CGIFx flag is cleared after the desired action is completed to avoid generating an immediate interrupt.

[Page 1]

### Assessment

Denies the erratum and supplies generic interrupt-flag advice.

- contradicted: States that both automatic disable and TEIFx reporting can fail. Denies that the active-channel global clear can cause the documented error omission/disable failure.
- missing: Identifies clearing GIFx in the same clock cycle as a transfer error as the trigger. Does not mention the same-clock-cycle race.
- missing: Uses specific event flags and clear bits instead of clearing active-channel GIFx. Does not prescribe individual event flags instead of active-channel GIFx clearing.

Citations: {'labels': [1], 'invalid_labels': [], 'resolved_page_ids': [70285], 'note': 'Valid local labels do not establish that the cited page supports the claim.'}

Slot 1 is manual interrupt-register guidance; it does not establish the silicon limitation.

Complete evidence shown: False

### Retrieved pages

- 1. st_stm32f103_refman_rm0008 p285 (ID 70285, score 0.6639156551327202)
- 2. st_stm32f407_refman_rm0090 p325 (ID 100325, score 0.6567172996442511)
- 3. st_stm32f407_refman_rm0090 p326 (ID 100326, score 0.6535190478403362)
- 4. st_stm32f103_errata_es096 p13 (ID 60013, score 0.6529741824497649)
- 5. st_stm32f103_refman_rm0008 p814 (ID 70814, score 0.6497651639402884)
- 6. st_stm32f103_refman_rm0008 p278 (ID 70278, score 0.6476274335296027)
- 7. st_stm32f103_refman_rm0008 p280 (ID 70280, score 0.6445637212528119)
- 8. st_stm32f407_errata_es0182 p17 (ID 90017, score 0.6436323083258213)
- 9. st_stm32f103_errata_es096 p23 (ID 60023, score 0.638551807762816)
- 10. st_stm32f103_errata_es096 p29 (ID 60029, score 0.6384747197672013)

## mcu-draft-005 — incorrect

On an STM32F407 with PH10 available in the package, EXTI10 is mapped to PH10 while EXTI2 remains mapped to PA2, but the interrupts do not work correctly. Is this pin combination supported?

Baseline: partial; improved: False
Shown page IDs: [80071, 80064, 80072]

### Saved model answer

The pin combination for EXTI10 on PH10 and EXTI2 on PA2 is supported by the STM32F407, as shown in Table 9 on Page 71 of the datasheet. However, the statement that the interrupts do not work correctly cannot be verified based solely on the provided information.

### Assessment

Uses nominal pin availability to deny the silicon limitation.

- contradicted: Rejects independent PH10/PA2 routing for the stated limitation. Explicitly says the PH10/PA2 combination is supported.
- missing: Explains that using PH10 requires EXTI2 and EXTI10 to select the same GPIO port. Does not explain the same-port requirement.

Citations: {'labels': [71], 'invalid_labels': [71], 'resolved_page_ids': [], 'note': 'Valid local labels do not establish that the cited page supports the claim.'}

Cites physical Page 71, which is an invalid local slot label; datasheet pin tables do not establish erratum compatibility.

Complete evidence shown: False

### Retrieved pages

- 1. st_stm32f407_datasheet_ds8626 p71 (ID 80071, score 0.6739175254487544)
- 2. st_stm32f407_datasheet_ds8626 p64 (ID 80064, score 0.6442939452162867)
- 3. st_stm32f407_datasheet_ds8626 p72 (ID 80072, score 0.6418610314534016)
- 4. st_stm32f407_datasheet_ds8626 p51 (ID 80051, score 0.6361720891109479)
- 5. st_stm32f407_datasheet_ds8626 p65 (ID 80065, score 0.6348901187117877)
- 6. st_stm32f407_datasheet_ds8626 p66 (ID 80066, score 0.6317660595612846)
- 7. st_stm32f407_datasheet_ds8626 p57 (ID 80057, score 0.6298399307487633)
- 8. st_stm32f407_errata_es0182 p11 (ID 90011, score 0.628972220523622)
- 9. st_stm32f407_datasheet_ds8626 p17 (ID 80017, score 0.6273263962523278)
- 10. st_stm32f407_datasheet_ds8626 p61 (ID 80061, score 0.6239437140370238)

## mcu-draft-006 — partial

On an STM32F407, a DMA write to an APB1 peripheral stalls when the CPU changes the AHB/APB1 prescaler from 1 to 4 during the transfer. What causes this, how can it be prevented, and how can the MCU recover?

Baseline: partial; improved: False
Shown page IDs: [90013, 100308, 100307]

### Saved model answer

The cause of the stall is due to the change in the AHB/APB1 prescaler value during the DMA transfer, which affects the timing of the DMA operations on the APB1 peripherals.

To prevent the stall, insert a dummy read operation to the PWR_CR register just after programming the DBP bit, or wait for the end of the operation via a polling loop on targeted registers.

For recovery, reset through the BDRST bit or write to the backup domain via a polling loop on targeted registers.

[Page 1]

### Assessment

Recognizes the trigger, largely restating the question, but prevention and recovery are both wrong.

- met: Identifies slowing the same APB from prescaler 1 to 4 during an active DMA write as the documented trigger. Connects the active APB1 DMA stall to changing the prescaler as stated in the question.
- contradicted: Waits for the DMA transfer on the affected APB to finish before slowing the clock. Prescribes DBP/PWR_CR handling from the backup-domain erratum, not waiting for affected APB DMA completion.
- contradicted: Names system reset as the documented recovery. Prescribes BDRST/backup-domain polling instead of system reset.

Citations: {'labels': [1], 'invalid_labels': [], 'resolved_page_ids': [90013], 'note': 'Valid local labels do not establish that the cited page supports the claim.'}

Slot 1 (ES0182 p13) is the unrelated backup-domain workaround.

Complete evidence shown: False

### Retrieved pages

- 1. st_stm32f407_errata_es0182 p13 (ID 90013, score 0.6847750148646541)
- 2. st_stm32f407_refman_rm0090 p308 (ID 100308, score 0.665417561831046)
- 3. st_stm32f407_refman_rm0090 p307 (ID 100307, score 0.6538246133821906)
- 4. st_stm32f407_refman_rm0090 p314 (ID 100314, score 0.6489406471132076)
- 5. st_stm32f103_refman_rm0008 p280 (ID 70280, score 0.639969648974027)
- 6. st_stm32f407_datasheet_ds8626 p23 (ID 80023, score 0.6392900581083185)
- 7. st_stm32f407_refman_rm0090 p313 (ID 100313, score 0.6286754498996302)
- 8. st_stm32f407_errata_es0182 p38 (ID 90038, score 0.6245769828464033)
- 9. st_stm32f407_errata_es0182 p11 (ID 90011, score 0.6219029337079875)
- 10. st_stm32f103_refman_rm0008 p279 (ID 70279, score 0.6205346029549078)

## mcu-draft-007 — partial

I'm migrating an STM32F407 LQFP100 board from silicon revision A to revision Z. Does the PDR_ON connection need to change, and can I continue using a 1.7 V supply?

Baseline: abstained; improved: True
Shown page IDs: [90011, 80026, 80027]

### Saved model answer

No modification is required when migrating to other device revisions for PDR_ON connection [Page 1]. However, it is no longer possible to supply the product from a 1.7 V VDD on LQFP100 package since VDD minimum value is 1.8 V when the POR/PDR feature is enabled [Page 2].

### Assessment

Correct voltage restriction, but incomplete and overgeneralized wiring guidance.

- partially_met: Requires the former PDR_ON pin to be tied to VSS on revision Z: change a VDD connection to VSS, or retain an existing VSS connection. Says no modification is required but omits that this holds only for an existing VSS connection; fails the VDD-to-VSS case.
- partially_met: Explains that POR/PDR is always enabled on revision Z in LQFP100. Uses the enabled-POR/PDR voltage rule without explaining that revision Z always enables POR/PDR.
- met: Rejects 1.7 V operation and gives the 1.8 V minimum. Rejects 1.7 V and states the 1.8 V minimum.

Citations: {'labels': [1, 2], 'invalid_labels': [], 'resolved_page_ids': [90011, 80026], 'note': 'Valid local labels do not establish that the cited page supports the claim.'}

The no-change statement drops the condition in slot 1; the revision-specific voltage restriction is also on slot 1, not adequately attributed.

Complete evidence shown: True

### Retrieved pages

- 1. st_stm32f407_errata_es0182 p11 (ID 90011, score 0.6719848678081752)
- 2. st_stm32f407_datasheet_ds8626 p26 (ID 80026, score 0.6424431356213286)
- 3. st_stm32f407_datasheet_ds8626 p27 (ID 80027, score 0.6250289218504281)
- 4. st_stm32f407_errata_es0182 p38 (ID 90038, score 0.6226062424116361)
- 5. st_stm32f407_datasheet_ds8626 p202 (ID 80202, score 0.6172515802213705)
- 6. st_stm32f407_datasheet_ds8626 p79 (ID 80079, score 0.6146945856978148)
- 7. st_stm32f407_refman_rm0090 p116 (ID 100116, score 0.613385716333716)
- 8. st_stm32f407_datasheet_ds8626 p16 (ID 80016, score 0.5893487024557718)
- 9. st_stm32f407_datasheet_ds8626 p28 (ID 80028, score 0.5875853164873514)
- 10. st_stm32f407_datasheet_ds8626 p199 (ID 80199, score 0.5791688333594539)

## mcu-draft-008 — correct

On an STM32F407, a write to an APB peripheral register immediately after enabling its RCC clock sometimes fails. How much delay is required, and what workaround does the errata recommend?

Baseline: incorrect; improved: True
Shown page IDs: [90012, 100249, 100245]

### Saved model answer

On an STM32F407, a write to an APB peripheral register immediately after enabling its RCC clock can fail due to a delay that depends on the peripheral mapping. The delay may be equal to 1 + (AHB/APB prescaler) cycles.

The errata recommends applying one of the following measures:
- Use the DSB instruction to stall the Arm® Cortex®-M4 CPU pipeline until the instruction has completed.
- Insert "n" NOPs between the RCC enable bit write and the peripheral register writes (n = 2 for AHB peripherals, n = 1 + AHB/APB prescaler for APB peripherals).
- Simply insert a dummy read operation from the corresponding register just after enabling the peripheral clock.

### Assessment

Both core facts are satisfied.

- met: Gives the delay as 1 plus the AHB/APB prescaler in CPU cycles. Gives the 1 + AHB/APB prescaler delay in cycles.
- met: Names sufficient NOPs, DSB, or the documented post-enable dummy read as a workaround. Names the documented DSB, NOP and dummy-read alternatives.

Citations: {'labels': [], 'invalid_labels': [], 'resolved_page_ids': [], 'note': 'Valid local labels do not establish that the cited page supports the claim.'}

No citation labels; content is supported by shown slot 1, but the answer fails the citation instruction.

Complete evidence shown: True

### Retrieved pages

- 1. st_stm32f407_errata_es0182 p12 (ID 90012, score 0.7433595342194009)
- 2. st_stm32f407_refman_rm0090 p249 (ID 100249, score 0.6799739115230536)
- 3. st_stm32f407_refman_rm0090 p245 (ID 100245, score 0.671488429574609)
- 4. st_stm32f407_refman_rm0090 p258 (ID 100258, score 0.6670083716289288)
- 5. st_stm32f103_refman_rm0008 p112 (ID 70112, score 0.6636226010595507)
- 6. st_stm32f407_refman_rm0090 p246 (ID 100246, score 0.6635620709106692)
- 7. st_stm32f407_refman_rm0090 p241 (ID 100241, score 0.6619676922104368)
- 8. st_stm32f103_refman_rm0008 p115 (ID 70115, score 0.6618159551504653)
- 9. st_stm32f407_errata_es0182 p23 (ID 90023, score 0.659097262366234)
- 10. st_stm32f407_refman_rm0090 p243 (ID 100243, score 0.6578898351350474)

## mcu-draft-009 — correct

On ESP32 chip revision v0.0, repeated consecutive writes to the same DPORT register address sometimes get lost, both for UART2 FIFO and for GPIO_OUT1_W1TC. What workaround should I use?

Baseline: incorrect; improved: True
Shown page IDs: [20016, 20013, 20033]

### Saved model answer

For UART2 FIFO and GPIO_OUT1_W1TC on ESP32 chip revision v0.0, use the equivalent AHB address instead of the DPORT address when writing the same register address in sequential instructions. This will prevent data loss due to the peripheral being mapped to two internal memory buses (AHB & DPORT) [Page 1].

### Assessment

The required workaround is correct for both registers. Exact addresses and FIFO-read caveats are optional in the frozen rubric.

- met: Uses the AHB register aliases for the affected consecutive writes. Explicitly uses equivalent AHB addresses instead of DPORT for both UART2 FIFO and GPIO_OUT1_W1TC consecutive writes.

Citations: {'labels': [1], 'invalid_labels': [], 'resolved_page_ids': [20016], 'note': 'Valid local labels do not establish that the cited page supports the claim.'}

Slot 1 (ESP32 errata p16) supports the advice for both registers.

Complete evidence shown: True

### Retrieved pages

- 1. espressif_esp32_errata p16 (ID 20016, score 0.7769646959986806)
- 2. espressif_esp32_errata p13 (ID 20013, score 0.6590684349439873)
- 3. espressif_esp32_errata p33 (ID 20033, score 0.6418719050885986)
- 4. espressif_esp32_errata p12 (ID 20012, score 0.639013493303458)
- 5. espressif_esp32_errata p10 (ID 20010, score 0.6381780504653194)
- 6. espressif_esp32_errata p32 (ID 20032, score 0.6311788078984406)
- 7. espressif_esp32_refman p135 (ID 30135, score 0.6277943064204257)
- 8. espressif_esp32_errata p15 (ID 20015, score 0.6256854343330227)
- 9. espressif_esp32_refman p139 (ID 30139, score 0.6200314778056842)
- 10. espressif_esp32_refman p138 (ID 30138, score 0.6197299238009523)

## mcu-draft-010 — partial

On ESP32 chip revision v3.1, can GPIO4 use a rising-edge interrupt while other GPIO0-31 pins also have interrupts enabled? If not, what level-triggered workaround does the errata describe?

Baseline: partial; improved: False
Shown page IDs: [20018, 10017, 20019]

### Saved model answer

On ESP32 chip revision v3.1, GPIO4 cannot use a rising-edge interrupt while other GPIO0-31 pins also have interrupts enabled due to the limitation described in [Page 1]. The errata describes a workaround: set the GPIO interrupt type to high after the CPU services the interrupt, then change it to low for a second interrupt that occurs at this time, which the CPU needs to ignore.

### Assessment

Recognizes the restriction but misses a group condition and gives an incorrectly ordered sequence.

- met: States the same-group edge/other-interrupt restriction. Rejects GPIO4 rising-edge interrupts alongside other interrupts in GPIO0-31.
- missing: Allows multiple level interrupts when no edge interrupt is configured. Does not state that multiple level interrupts are allowed when no edge interrupts remain.
- partially_met: Gives high then low triggering and ignores the second interrupt. Mentions high/low and ignoring the second interrupt, but places initial high configuration after servicing the interrupt, corrupting the sequence.

Citations: {'labels': [1], 'invalid_labels': [], 'resolved_page_ids': [20018], 'note': 'Valid local labels do not establish that the cited page supports the claim.'}

Cites slot 1; required sequence continues on slot 3 and is paraphrased incorrectly.

Complete evidence shown: True

### Retrieved pages

- 1. espressif_esp32_errata p18 (ID 20018, score 0.7152630491385822)
- 2. espressif_esp32_datasheet p17 (ID 10017, score 0.6634047022404651)
- 3. espressif_esp32_errata p19 (ID 20019, score 0.662273475302944)
- 4. espressif_esp32_refman p146 (ID 30146, score 0.6527854372046374)
- 5. espressif_esp32_errata p32 (ID 20032, score 0.6491405379358886)
- 6. espressif_esp32_refman p142 (ID 30142, score 0.6402151612289669)
- 7. rpi_rp2040_datasheet p255 (ID 40255, score 0.6398222469402565)
- 8. espressif_esp32_refman p135 (ID 30135, score 0.6392112084246808)
- 9. espressif_esp32_refman p143 (ID 30143, score 0.636781095534219)
- 10. espressif_esp32_refman p153 (ID 30153, score 0.6366438308403518)

## mcu-draft-011 — partial

Can ESP32 chip revision v3.1 use EXT0 wake-up together with the ULP coprocessor and touch wake-up during Deep Sleep?

Baseline: abstained; improved: True
Shown page IDs: [20017, 20032, 30191]

### Saved model answer

No, ESP32 chip revision v3.1 cannot use EXT0 wake-up together with the ULP coprocessor and touch wake-up during Deep Sleep. According to Page 3 (document espressif_esp32_refman, page 191), in Deep-sleep mode, only RTC GPIOs (not DIGITAL GPIOs) can work as wakeup source. Therefore, the ULP co-processor and touch sensor functionalities are not available in Deep-sleep mode if RTC_PERIPH is powered up [Page 1].

### Assessment

Correct decision and one side of the power-domain restriction, without the required full incompatibility explanation.

- met: Rejects simultaneous EXT0 and ULP/touch in the stated Deep-sleep setup. Rejects the requested simultaneous wake-up combination.
- partially_met: Explains that the wake sources require incompatible RTC_PERIPH power settings. States RTC_PERIPH powered up prevents ULP/touch but omits that EXT0 requires powered-up RTC_PERIPH; adds an unrelated GPIO-wake rationale.

Citations: {'labels': [3, 191, 1], 'invalid_labels': [191], 'resolved_page_ids': [30191, 20017], 'note': 'Valid local labels do not establish that the cited page supports the claim.'}

Slot 1 supports the ULP/touch restriction; slot 3's GPIO wake statement does not establish the EXT0 power conflict.

Complete evidence shown: True

### Retrieved pages

- 1. espressif_esp32_errata p17 (ID 20017, score 0.7168675960795214)
- 2. espressif_esp32_errata p32 (ID 20032, score 0.7046431525947154)
- 3. espressif_esp32_refman p191 (ID 30191, score 0.6826537678485092)
- 4. espressif_esp32_datasheet p31 (ID 10031, score 0.6763394082428982)
- 5. espressif_esp32_datasheet p30 (ID 10030, score 0.6709036927666053)
- 6. espressif_esp32_refman p180 (ID 30180, score 0.6491880735417634)
- 7. espressif_esp32_errata p20 (ID 20020, score 0.633546888191964)
- 8. st_stm32f103_errata_es096 p9 (ID 60009, score 0.6310032959641365)
- 9. espressif_esp32_refman p190 (ID 30190, score 0.625375500991991)
- 10. espressif_esp32_refman p199 (ID 30199, score 0.6197676573422313)

## mcu-draft-012 — correct

On ESP32 revision v0.0, changing Audio PLL sdm0 and sdm1 does not provide the expected frequency precision. Is this a hardware limitation, and was it fixed in later revisions?

Baseline: partial; improved: True
Shown page IDs: [30171, 20021, 10077]

### Saved model answer

Yes, it is a hardware limitation. The formula for calculating the Audio PLL frequency on revision v0.0 is limited by not using configuration registers sdm0 & sdm1, which affects the range and precision of PLL frequencies [Page 2]. This issue was fixed in chip revision v1.0 [Page 2].

### Assessment

Both core facts are satisfied.

- met: Identifies ignored sdm0 and sdm1 on chip v0.0. States sdm0 and sdm1 are unused on v0.0.
- met: Identifies chip v1.0 as fixed. Explicitly identifies v1.0 as the fix.

Citations: {'labels': [2, 2], 'invalid_labels': [], 'resolved_page_ids': [20021], 'note': 'Valid local labels do not establish that the cited page supports the claim.'}

Slot 2 (ESP32 errata p21) supports both facts.

Complete evidence shown: True

### Retrieved pages

- 1. espressif_esp32_refman p171 (ID 30171, score 0.6911216993419633)
- 2. espressif_esp32_errata p21 (ID 20021, score 0.689637853893866)
- 3. espressif_esp32_datasheet p77 (ID 10077, score 0.6227541315470371)
- 4. st_stm32f407_datasheet_ds8626 p38 (ID 80038, score 0.6186998403182786)
- 5. espressif_esp32_datasheet p75 (ID 10075, score 0.6108749183524007)
- 6. espressif_esp32_datasheet p76 (ID 10076, score 0.6064465924828578)
- 7. espressif_esp32_errata p10 (ID 20010, score 0.6029810191002424)
- 8. espressif_esp32_errata p1 (ID 20001, score 0.6002440023805586)
- 9. espressif_esp32_datasheet p11 (ID 10011, score 0.5998498938237585)
- 10. espressif_esp32_datasheet p44 (ID 10044, score 0.5961536003102628)
