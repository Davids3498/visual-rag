# MCU RAG evaluation — corrected

Original run: 2026-09-08T16:54:44.583357+00:00

Verdicts: {'correct': 3, 'partial': 8, 'incorrect': 1, 'abstained': 0, 'uncertain': 0}
Improved verdicts: 7/12
Complete core evidence shown: 11/12

- ndcg_at_10: 0.936924 (mean)
- recall_at_10: 1.000000 (mean)
- recall_at_3: 0.875000 (mean)

Verdict transitions only: incorrect/abstained to partial/correct, or partial to correct. Additional facts within an unchanged partial verdict are not counted.

## Limitations

- Gold annotations are provisional; answer judgments require semantic review.

## mcu-draft-001 — partial

On an STM32F103C8, USART1 is clocked and PA12 is configured as an alternate-function output for USART1 RTS, but PA12 stays high. CAN is unused and its clock is disabled. What could cause this, and how can I fix it?

Baseline: incorrect; improved: True
Shown page IDs: [60010, 60013, 60011]

### Saved model answer

[Page 1] The issue might be due to the fact that when CAN is not clocked, the signal on PA12 remains high by default if it is configured as an alternate function output for USART1 RTS.

[Page 3] To fix this, remap the CAN to another IO configuration through the CAN_REMAP bits of the AFIO_MAPR register.

### Assessment

The diagnosis is present; the mandatory unused-remap choice is missing.

- met: Identifies the CAN/USART1_RTS conflict on PA12. Links unclocked CAN and PA12 staying high in the stated RTS configuration.
- partially_met: Specifies selecting the unused CAN remap when CAN is unused. Recommends CAN remapping but does not select the unused configuration when CAN is unused.

Citations: {'labels': [1, 3], 'invalid_labels': [], 'resolved_page_ids': [60010, 60011], 'note': 'Valid local labels do not establish that the cited page supports the claim.'}

The cause cites the correct page. The workaround cites slot 3 (ES096 p11), which does not contain the CAN workaround.

Complete evidence shown: True

### Retrieved pages

- 1. st_stm32f103_errata_es096 p10 (ID 60010, score 44.28125)
- 2. st_stm32f103_errata_es096 p13 (ID 60013, score 43.0625)
- 3. st_stm32f103_errata_es096 p11 (ID 60011, score 42.75)
- 4. st_stm32f103_errata_es096 p12 (ID 60012, score 41.46875)
- 5. st_stm32f103_errata_es096 p22 (ID 60022, score 40.28125)
- 6. st_stm32f103_errata_es096 p21 (ID 60021, score 40.09375)
- 7. st_stm32f407_errata_es0182 p26 (ID 90026, score 39.90625)
- 8. st_stm32f103_errata_es096 p28 (ID 60028, score 39.875)
- 9. st_stm32f407_errata_es0182 p24 (ID 90024, score 39.875)
- 10. st_stm32f103_datasheet_ds5319 p19 (ID 50019, score 39.59375)

## mcu-draft-002 — correct

On an STM32F103x8/xB, TIM3 channel 2 on PB5 stays high with TIM3 and I2C1 both clocked and PB5 configured as an alternate-function output. SMBus Alert is unused. Why does this happen, and what use of CH2 does the errata permit in this configuration?

Baseline: incorrect; improved: True
Shown page IDs: [60012, 60013, 90022]

### Saved model answer

[Page 1] When TIM3 and I2C1 are both clocked and PB5 is configured as an alternate function output, there is a conflict between the TIM3_CH2 signal and the I2C1 SMBA signal. [Page 1] To avoid this conflict, TIM3_CH2 can only be used in input mode.

### Assessment

Both core facts are satisfied in the stated scenario. Exact underscore formatting is irrelevant.

- met: Explains the I2C1_SMBA conflict despite unused alert. Identifies the TIM3_CH2/I2C1_SMBA conflict under the question's explicitly unused-SMBus-Alert premise; does not require SMBA to be enabled.
- met: Restricts CH2 to input in the stated configuration. Explicitly restricts TIM3_CH2 to input mode.

Citations: {'labels': [1, 1], 'invalid_labels': [], 'resolved_page_ids': [60012], 'note': 'Valid local labels do not establish that the cited page supports the claim.'}

Both claims cite slot 1, ES096 p12, which supports them.

Complete evidence shown: True

### Retrieved pages

- 1. st_stm32f103_errata_es096 p12 (ID 60012, score 54.71875)
- 2. st_stm32f103_errata_es096 p13 (ID 60013, score 47.15625)
- 3. st_stm32f407_errata_es0182 p22 (ID 90022, score 45.625)
- 4. st_stm32f103_datasheet_ds5319 p32 (ID 50032, score 45.5625)
- 5. st_stm32f103_datasheet_ds5319 p11 (ID 50011, score 44.875)
- 6. st_stm32f103_refman_rm0008 p178 (ID 70178, score 44.5625)
- 7. st_stm32f103_datasheet_ds5319 p33 (ID 50033, score 44.375)
- 8. st_stm32f103_datasheet_ds5319 p12 (ID 50012, score 44.125)
- 9. st_stm32f407_refman_rm0090 p839 (ID 100839, score 44.09375)
- 10. st_stm32f407_errata_es0182 p11 (ID 90011, score 43.625)

## mcu-draft-003 — incorrect

On an STM32F103x8/xB, after updating the independent watchdog settings and immediately entering Stop mode, the next watchdog update hangs and eventually resets the MCU. How can this be prevented?

Baseline: incorrect; improved: False
Shown page IDs: [60008, 60007, 50018]

### Saved model answer

To prevent this issue, ensure that the independent watchdog counter is frozen in debug mode before entering Stop mode. This can be achieved by setting the appropriate bit in the option bytes of the STM32F103x8/xB device. Refer to the section on "Independent watchdog" in the STM32F103x8/xB datasheet for more details on how to configure the watchdog settings correctly. [Page 3]

### Assessment

Substitutes debug watchdog freezing for the erratum workaround. The gold page is rank 6 and was not shown.

- missing: Waits for RVU and PVU to clear before Stop. Does not wait for RVU/PVU to clear.
- missing: Explains that entering Stop before the watchdog update completes can leave the flags set and block later updates. Does not explain the stuck update flags or subsequent blocked writes.

Citations: {'labels': [3], 'invalid_labels': [], 'resolved_page_ids': [50018], 'note': 'Valid local labels do not establish that the cited page supports the claim.'}

The cited datasheet page cannot establish the required update-before-Stop workaround.

Complete evidence shown: False

### Retrieved pages

- 1. st_stm32f103_errata_es096 p8 (ID 60008, score 33.90625)
- 2. st_stm32f103_errata_es096 p7 (ID 60007, score 33.5)
- 3. st_stm32f103_datasheet_ds5319 p18 (ID 50018, score 33.1875)
- 4. st_stm32f407_errata_es0182 p9 (ID 90009, score 33.0)
- 5. st_stm32f103_errata_es096 p23 (ID 60023, score 32.46875)
- 6. st_stm32f103_errata_es096 p17 (ID 60017, score 32.28125)
- 7. st_stm32f407_datasheet_ds8626 p35 (ID 80035, score 32.1875)
- 8. st_stm32f407_errata_es0182 p19 (ID 90019, score 32.09375)
- 9. st_stm32f407_refman_rm0090 p704 (ID 100704, score 32.09375)
- 10. st_stm32f407_errata_es0182 p10 (ID 90010, score 31.625)

## mcu-draft-004 — partial

On an STM32F103x8/xB, can clearing a DMA channel's global interrupt flag while the channel is active cause a transfer error to be missed or prevent automatic channel disable? How should software avoid this?

Baseline: partial; improved: False
Shown page IDs: [60013, 90016, 90030]

### Saved model answer

On an STM32F103x8/xB, clearing a DMA channel's global interrupt flag while the channel is active can cause a transfer error to be missed or prevent automatic channel disable. To avoid this, software should not clear GIFx flags when the channel is active. Instead, use HTIFx, TCIFx, and TEIFx specific event flags and their corresponding clear bits [Page 1].

### Assessment

Correct consequence and workaround, but the required same-clock-cycle trigger is absent.

- met: States that both automatic disable and TEIFx reporting can fail. Describes lost transfer-error reporting and failed automatic disable.
- missing: Identifies clearing GIFx in the same clock cycle as a transfer error as the trigger. Does not identify coincidence of the GIFx clear and transfer error in the same clock cycle.
- met: Uses specific event flags and clear bits instead of clearing active-channel GIFx. Explicitly uses HTIFx, TCIFx, TEIFx and their clear bits instead of active-channel GIFx clearing.

Citations: {'labels': [1], 'invalid_labels': [], 'resolved_page_ids': [60013], 'note': 'Valid local labels do not establish that the cited page supports the claim.'}

The cited ES096 p13 supports the stated consequence and workaround; citation does not make the omitted trigger present.

Complete evidence shown: True

### Retrieved pages

- 1. st_stm32f103_errata_es096 p13 (ID 60013, score 38.71875)
- 2. st_stm32f407_errata_es0182 p16 (ID 90016, score 34.625)
- 3. st_stm32f407_errata_es0182 p30 (ID 90030, score 34.59375)
- 4. st_stm32f407_errata_es0182 p17 (ID 90017, score 34.28125)
- 5. st_stm32f103_refman_rm0008 p280 (ID 70280, score 33.75)
- 6. st_stm32f103_errata_es096 p3 (ID 60003, score 33.5625)
- 7. st_stm32f103_refman_rm0008 p284 (ID 70284, score 33.34375)
- 8. st_stm32f103_refman_rm0008 p287 (ID 70287, score 32.96875)
- 9. st_stm32f407_refman_rm0090 p326 (ID 100326, score 32.9375)
- 10. st_stm32f407_errata_es0182 p29 (ID 90029, score 32.5)

## mcu-draft-005 — partial

On an STM32F407 with PH10 available in the package, EXTI10 is mapped to PH10 while EXTI2 remains mapped to PA2, but the interrupts do not work correctly. Is this pin combination supported?

Baseline: partial; improved: False
Shown page IDs: [90011, 100299, 100294]

### Saved model answer

No, this pin combination is not supported. According to Page 2 of document RM0090, bits 15:0 of SYSCFG_EXTICR3 must be programmed to the same value to select PH10/PH2 or PI10/PI2 as external interrupt inputs. Since PA2 is already mapped to EXTI2, changing it to PH10 would conflict with the requirement for matching bit values. Therefore, mapping EXTI10 to PH10 and EXTI2 to PA2 simultaneously is not supported.

### Assessment

Correctly rejects PH10/PA2, but the required EXTI2/EXTI10 same-port explanation is corrupted by incorrect register-field instructions.

- met: Rejects independent PH10/PA2 routing for the stated limitation. Rejects the PH10/PA2 combination.
- partially_met: Explains that using PH10 requires EXTI2 and EXTI10 to select the same GPIO port. Mentions matching values and PH10/PH2, but incorrectly describes bits 15:0 of EXTICR3 as the matching fields and confuses remapping EXTI2 with changing it to PH10.

Citations: {'labels': [2], 'invalid_labels': [], 'resolved_page_ids': [100299], 'note': 'Valid local labels do not establish that the cited page supports the claim.'}

Attributes the erratum to slot 2 (RM0090 p299); that page defines register encodings and does not establish the silicon limitation.

Complete evidence shown: True

### Retrieved pages

- 1. st_stm32f407_errata_es0182 p11 (ID 90011, score 39.34375)
- 2. st_stm32f407_refman_rm0090 p299 (ID 100299, score 34.28125)
- 3. st_stm32f407_refman_rm0090 p294 (ID 100294, score 34.0625)
- 4. st_stm32f407_datasheet_ds8626 p43 (ID 80043, score 34.0)
- 5. st_stm32f407_datasheet_ds8626 p25 (ID 80025, score 33.53125)
- 6. st_stm32f407_refman_rm0090 p301 (ID 100301, score 33.5)
- 7. st_stm32f407_datasheet_ds8626 p48 (ID 80048, score 33.375)
- 8. st_stm32f407_refman_rm0090 p295 (ID 100295, score 33.125)
- 9. st_stm32f103_refman_rm0008 p192 (ID 70192, score 32.78125)
- 10. st_stm32f407_datasheet_ds8626 p50 (ID 80050, score 32.34375)

## mcu-draft-006 — partial

On an STM32F407, a DMA write to an APB1 peripheral stalls when the CPU changes the AHB/APB1 prescaler from 1 to 4 during the transfer. What causes this, how can it be prevented, and how can the MCU recover?

Baseline: partial; improved: False
Shown page IDs: [90011, 90013, 90016]

### Saved model answer

On an STM32F407, a DMA write to an APB1 peripheral stalls when the CPU changes the AHB/APB1 prescaler from 1 to 4 during the transfer due to a clock frequency relationship that causes data corruption [Page 2].

To prevent this, avoid the above-mentioned clock frequency relationship by applying one of the following measures: incrementing the APB frequency, decreasing the transfer bandwidth, or reducing SDIO_CK frequency [Page 2].

The MCU recovers by waiting until the end of the DMA transfer on the affected APB before changing the prescaler [Page 2].

### Assessment

Contains part of the prevention sequence, but misapplies it as recovery and imports unrelated clock/SDIO advice. Partial recognition does not make this an actionable correct answer.

- partially_met: Identifies slowing the same APB from prescaler 1 to 4 during an active DMA write as the documented trigger. Repeats the documented prescaler-change trigger, but incorrectly explains it as a clock relationship causing data corruption.
- partially_met: Waits for the DMA transfer on the affected APB to finish before slowing the clock. States waiting for the affected APB DMA to finish before changing the prescaler, but mislabels it as recovery and gives unrelated bandwidth/SDIO clock changes as prevention.
- contradicted: Names system reset as the documented recovery. Claims waiting for the blocked DMA to finish recovers the MCU; omits the required system reset.

Citations: {'labels': [2, 2, 2], 'invalid_labels': [], 'resolved_page_ids': [90013], 'note': 'Valid local labels do not establish that the cited page supports the claim.'}

All claims cite slot 2 (ES0182 p13), which does not establish the required DMA workaround or system-reset recovery. The relevant erratum is on slot 1.

Complete evidence shown: True

### Retrieved pages

- 1. st_stm32f407_errata_es0182 p11 (ID 90011, score 47.6875)
- 2. st_stm32f407_errata_es0182 p13 (ID 90013, score 45.90625)
- 3. st_stm32f407_errata_es0182 p16 (ID 90016, score 40.96875)
- 4. st_stm32f103_errata_es096 p24 (ID 60024, score 40.375)
- 5. st_stm32f407_errata_es0182 p19 (ID 90019, score 39.96875)
- 6. st_stm32f407_errata_es0182 p27 (ID 90027, score 39.75)
- 7. st_stm32f103_datasheet_ds5319 p49 (ID 50049, score 39.34375)
- 8. st_stm32f407_errata_es0182 p12 (ID 90012, score 39.15625)
- 9. st_stm32f103_errata_es096 p16 (ID 60016, score 38.46875)
- 10. espressif_esp32_errata p15 (ID 20015, score 38.375)

## mcu-draft-007 — partial

I'm migrating an STM32F407 LQFP100 board from silicon revision A to revision Z. Does the PDR_ON connection need to change, and can I continue using a 1.7 V supply?

Baseline: abstained; improved: True
Shown page IDs: [90011, 80027, 80193]

### Saved model answer

[Page 1] Applications using revision A devices with PDR_ON pin connected to VDD (POR/PDR feature enabled) should connect the former PDR_ON pin to VSS on revision Z devices. [Page 2] The PDR = 1.7 V for reduce temperature range; PDR = 1.8 V for all temperature range. Therefore, you can continue using a 1.7 V supply when migrating from revision A to revision Z.

### Assessment

The VDD-to-VSS wiring instruction is correct, but the supply-voltage conclusion is wrong. Classified partial for that correct portion only; the answer must not be treated as acceptable design advice.

- partially_met: Requires the former PDR_ON pin to be tied to VSS on revision Z: change a VDD connection to VSS, or retain an existing VSS connection. Correctly changes an existing VDD connection to VSS, but does not cover retaining an existing VSS connection.
- missing: Explains that POR/PDR is always enabled on revision Z in LQFP100. Does not explain that POR/PDR is always enabled on revision Z in LQFP100.
- contradicted: Rejects 1.7 V operation and gives the 1.8 V minimum. Explicitly permits continuing with 1.7 V, contradicting the erratum's 1.8 V minimum for this package and revision.

Citations: {'labels': [1, 2], 'invalid_labels': [], 'resolved_page_ids': [90011, 80027], 'note': 'Valid local labels do not establish that the cited page supports the claim.'}

Slot 1 supports the wiring change and also contains the 1.8 V restriction. The answer uses a datasheet statement from slot 2 to override that revision/package-specific restriction incorrectly.

Complete evidence shown: True

### Retrieved pages

- 1. st_stm32f407_errata_es0182 p11 (ID 90011, score 39.0)
- 2. st_stm32f407_datasheet_ds8626 p27 (ID 80027, score 36.53125)
- 3. st_stm32f407_datasheet_ds8626 p193 (ID 80193, score 36.46875)
- 4. st_stm32f407_datasheet_ds8626 p26 (ID 80026, score 35.65625)
- 5. st_stm32f407_datasheet_ds8626 p19 (ID 80019, score 35.625)
- 6. st_stm32f407_datasheet_ds8626 p18 (ID 80018, score 35.625)
- 7. st_stm32f407_errata_es0182 p10 (ID 90010, score 35.53125)
- 8. st_stm32f407_datasheet_ds8626 p31 (ID 80031, score 35.53125)
- 9. st_stm32f407_datasheet_ds8626 p61 (ID 80061, score 35.21875)
- 10. st_stm32f407_errata_es0182 p38 (ID 90038, score 35.03125)

## mcu-draft-008 — correct

On an STM32F407, a write to an APB peripheral register immediately after enabling its RCC clock sometimes fails. How much delay is required, and what workaround does the errata recommend?

Baseline: incorrect; improved: True
Shown page IDs: [90012, 90019, 90011]

### Saved model answer

On an STM32F407, a write to an APB peripheral register immediately after enabling its RCC clock may fail due to a delay that depends on the peripheral mapping. The delay can be equal to 1 + (AHB/APB prescaler) cycles.

The errata recommends applying one of the following measures as a workaround:
- Use the DSB instruction to stall the Arm® Cortex®-M4 CPU pipeline until the instruction has completed.
- Insert "n" NOPs between the RCC enable bit write and the peripheral register writes (n = 2 for AHB peripherals, n = 1 + AHB/APB prescaler for APB peripherals).
- Simply insert a dummy read operation from the corresponding register just after enabling the peripheral clock.

### Assessment

All core requirements are satisfied; optional AHB detail does not invalidate the APB answer.

- met: Gives the delay as 1 plus the AHB/APB prescaler in CPU cycles. Gives the documented 1 + AHB/APB prescaler delay in cycles.
- met: Names sufficient NOPs, DSB, or the documented post-enable dummy read as a workaround. Lists documented DSB, NOP and dummy-read alternatives.

Citations: {'labels': [], 'invalid_labels': [], 'resolved_page_ids': [], 'note': 'Valid local labels do not establish that the cited page supports the claim.'}

No page labels appear in this answer. The core content is correct and supported by shown slot 1, but it fails the prompt's citation requirement.

Complete evidence shown: True

### Retrieved pages

- 1. st_stm32f407_errata_es0182 p12 (ID 90012, score 32.9375)
- 2. st_stm32f407_errata_es0182 p19 (ID 90019, score 32.0625)
- 3. st_stm32f407_errata_es0182 p11 (ID 90011, score 31.8125)
- 4. st_stm32f407_errata_es0182 p7 (ID 90007, score 31.671875)
- 5. st_stm32f407_errata_es0182 p13 (ID 90013, score 31.609375)
- 6. st_stm32f407_errata_es0182 p20 (ID 90020, score 31.109375)
- 7. st_stm32f407_errata_es0182 p41 (ID 90041, score 31.078125)
- 8. st_stm32f407_errata_es0182 p30 (ID 90030, score 30.9375)
- 9. st_stm32f407_errata_es0182 p27 (ID 90027, score 30.890625)
- 10. st_stm32f407_errata_es0182 p29 (ID 90029, score 30.703125)

## mcu-draft-009 — partial

On ESP32 chip revision v0.0, repeated consecutive writes to the same DPORT register address sometimes get lost, both for UART2 FIFO and for GPIO_OUT1_W1TC. What workaround should I use?

Baseline: incorrect; improved: True
Shown page IDs: [20016, 20015, 20024]

### Saved model answer

For UART2 FIFO, use the equivalent AHB address not the DPORT address when writing the same register address in sequential instructions ([Page 1]). For GPIO_OUT1_W1TC, disable CPU interrupts before reading these five FIFO registers and enable CPU interrupts after read access ([Page 2]).

### Assessment

Only one of the two named registers receives the correct workaround. No penalty is applied for omitting optional exact addresses.

- partially_met: Uses the AHB register aliases for the affected consecutive writes. Correctly uses the AHB alias for UART2, but gives a FIFO-read interrupt workaround for GPIO_OUT1_W1TC instead of using its AHB alias.

Citations: {'labels': [1, 2], 'invalid_labels': [], 'resolved_page_ids': [20016, 20015], 'note': 'Valid local labels do not establish that the cited page supports the claim.'}

UART2 claim cites the right page. The GPIO advice is imported from the unrelated FIFO-read erratum on slot 2.

Complete evidence shown: True

### Retrieved pages

- 1. espressif_esp32_errata p16 (ID 20016, score 37.8125)
- 2. espressif_esp32_errata p15 (ID 20015, score 32.65625)
- 3. espressif_esp32_errata p24 (ID 20024, score 31.859375)
- 4. espressif_esp32_errata p12 (ID 20012, score 31.65625)
- 5. espressif_esp32_errata p20 (ID 20020, score 31.15625)
- 6. espressif_esp32_errata p18 (ID 20018, score 30.640625)
- 7. espressif_esp32_refman p150 (ID 30150, score 29.734375)
- 8. espressif_esp32_errata p13 (ID 20013, score 29.59375)
- 9. espressif_esp32_errata p30 (ID 20030, score 29.578125)
- 10. espressif_esp32_errata p23 (ID 20023, score 29.546875)

## mcu-draft-010 — partial

On ESP32 chip revision v3.1, can GPIO4 use a rising-edge interrupt while other GPIO0-31 pins also have interrupts enabled? If not, what level-triggered workaround does the errata describe?

Baseline: partial; improved: False
Shown page IDs: [20018, 20019, 20009]

### Saved model answer

On ESP32 chip revision v3.1, GPIO4 cannot use a rising-edge interrupt while other GPIO0-31 pins also have interrupts enabled due to the limitation described in [GPIO-3.14] on Page 18. The errata describes a workaround: set the GPIO interrupt type to high for the desired GPIO pin before triggering the interrupt, then change it to low after the CPU services the interrupt. This ensures that the CPU ignores the interrupt service routine during the second interrupt, allowing the desired GPIO interrupt to be triggered on a rising edge.

### Assessment

Recognizes the restriction and most of the sequence, but omits a required group condition and incompletely explains second-interrupt handling.

- met: States the same-group edge/other-interrupt restriction. Correctly rejects the edge interrupt alongside other interrupts in GPIO0-31.
- missing: Allows multiple level interrupts when no edge interrupt is configured. Does not explain that multiple level interrupts are allowed only when no edge interrupts remain in the group.
- partially_met: Gives high then low triggering and ignores the second interrupt. Gives high-then-low switching and mentions ignoring the second ISR, but presents ignoring as automatic rather than a software action.

Citations: {'labels': [18], 'invalid_labels': [18], 'resolved_page_ids': [], 'note': 'Valid local labels do not establish that the cited page supports the claim.'}

Uses physical Page 18 instead of local slot 1 or 2. This is an invalid citation label under the prompt, not a valid resolved citation.

Complete evidence shown: True

### Retrieved pages

- 1. espressif_esp32_errata p18 (ID 20018, score 38.875)
- 2. espressif_esp32_errata p19 (ID 20019, score 36.75)
- 3. espressif_esp32_errata p9 (ID 20009, score 34.75)
- 4. espressif_esp32_errata p16 (ID 20016, score 33.25)
- 5. espressif_esp32_refman p146 (ID 30146, score 33.125)
- 6. espressif_esp32_errata p23 (ID 20023, score 33.0)
- 7. espressif_esp32_refman p153 (ID 30153, score 32.96875)
- 8. espressif_esp32_errata p17 (ID 20017, score 32.6875)
- 9. espressif_esp32_datasheet p24 (ID 10024, score 31.984375)
- 10. espressif_esp32_refman p142 (ID 30142, score 31.96875)

## mcu-draft-011 — partial

Can ESP32 chip revision v3.1 use EXT0 wake-up together with the ULP coprocessor and touch wake-up during Deep Sleep?

Baseline: abstained; improved: True
Shown page IDs: [20017, 30191, 20009]

### Saved model answer

No, it cannot. According to Page 1, if the RTC_PERIPH power domain remains powered up, the ULP coprocessor and touch sensor will receive the wake-up signal earlier than the clock management module, leading to inaccuracies in the operating clock. Therefore, in Deep-sleep mode, if RTC_PERIH is powered up, the ULP co-processor and touch sensor cannot be used.

### Assessment

Correct decision and one side of the power-domain restriction; the incompatibility explanation is incomplete.

- met: Rejects simultaneous EXT0 and ULP/touch in the stated Deep-sleep setup. Explicitly rejects simultaneous EXT0 with ULP/touch.
- partially_met: Explains that the wake sources require incompatible RTC_PERIPH power settings. States that powered-up RTC_PERIPH prevents ULP/touch, but does not explain that EXT0 requires that same domain powered up.

Citations: {'labels': [1], 'invalid_labels': [], 'resolved_page_ids': [20017], 'note': 'Valid local labels do not establish that the cited page supports the claim.'}

Slot 1 (ESP32 errata p17) supports the ULP/touch clock explanation. The answer still omits the EXT0 power-up requirement needed to explain the conflict.

Complete evidence shown: True

### Retrieved pages

- 1. espressif_esp32_errata p17 (ID 20017, score 30.109375)
- 2. espressif_esp32_refman p191 (ID 30191, score 29.375)
- 3. espressif_esp32_errata p9 (ID 20009, score 26.609375)
- 4. espressif_esp32_datasheet p31 (ID 10031, score 26.328125)
- 5. espressif_esp32_refman p190 (ID 30190, score 26.15625)
- 6. espressif_esp32_errata p16 (ID 20016, score 25.953125)
- 7. espressif_esp32_refman p180 (ID 30180, score 25.90625)
- 8. espressif_esp32_refman p189 (ID 30189, score 25.84375)
- 9. espressif_esp32_datasheet p30 (ID 10030, score 25.8125)
- 10. espressif_esp32_refman p186 (ID 30186, score 25.734375)

## mcu-draft-012 — correct

On ESP32 revision v0.0, changing Audio PLL sdm0 and sdm1 does not provide the expected frequency precision. Is this a hardware limitation, and was it fixed in later revisions?

Baseline: partial; improved: True
Shown page IDs: [20021, 30171, 10077]

### Saved model answer

Yes, it is a hardware limitation. The formula for calculating the Audio PLL frequency on chip revision v0.0 is limited by the use of configuration registers sdm0 & sdm1, which are not used when configuring the Audio PLL. This issue was fixed in chip revision v1.0, where the formula uses sdm0, sdm1, sdm2, and odiv to calculate the frequency more precisely [Page 1].

### Assessment

Both core facts are satisfied; no formula is required.

- met: Identifies ignored sdm0 and sdm1 on chip v0.0. Explicitly says sdm0 and sdm1 are not used on v0.0, despite awkward introductory wording.
- met: Identifies chip v1.0 as fixed. Explicitly identifies chip v1.0 as the fix.

Citations: {'labels': [1], 'invalid_labels': [], 'resolved_page_ids': [20021], 'note': 'Valid local labels do not establish that the cited page supports the claim.'}

Slot 1 (ESP32 errata p21) supports both facts.

Complete evidence shown: True

### Retrieved pages

- 1. espressif_esp32_errata p21 (ID 20021, score 37.0625)
- 2. espressif_esp32_refman p171 (ID 30171, score 33.375)
- 3. espressif_esp32_datasheet p77 (ID 10077, score 28.78125)
- 4. st_stm32f407_datasheet_ds8626 p38 (ID 80038, score 27.875)
- 5. espressif_esp32_errata p23 (ID 20023, score 26.734375)
- 6. espressif_esp32_datasheet p70 (ID 10070, score 26.546875)
- 7. espressif_esp32_datasheet p11 (ID 10011, score 26.5)
- 8. espressif_esp32_errata p20 (ID 20020, score 26.359375)
- 9. espressif_esp32_refman p170 (ID 30170, score 26.28125)
- 10. espressif_esp32_errata p22 (ID 20022, score 26.28125)
