import torch
import torch.nn as nn

from model.encoder import ConformerEncoder
from model.decoder import Decoder
from model.module import Linear

class Conformer(nn.Module):
    """
     Inputs: inputs
        - **inputs** (batch, time, dim): Tensor containing input vector
        - **input_lengths** (batch): list of sequence input lengths
    Returns: outputs, output_lengths
        - **outputs** (batch, out_channels, time): Tensor produces by conformer.
        - **output_lengths** (batch): list of sequence output lengths
    """

    def __init__(
            self,
            args,
            n_classes,
            input_dim=80,
            encoder_dim=512,
            decoder_dim=512,
            n_encoder_layers=17,
            n_decoder_layers=1,
            n_heads=8,
            FFN_expansion_factor=4,
            conv_expansion_factor=2,
            input_dropout=0.1,
            FFN_dropout=0.1,
            attn_dropout=0.1,
            conv_dropout=0.1,
            decoder_dropout=0.1,
            kernel_size=31,
            half_step_residual=True,
            rnn_type='lstm',
            sos_id=2001,
            eos_id=2002,
            teacher_forcing=0.0
    ):
        super(Conformer, self).__init__()

        self.teacher_forcing_p = teacher_forcing
        self.args = args
        self.sos_id = sos_id
        self.eos_id = eos_id

        self.encoder = ConformerEncoder(
            args=args,
            input_dim=input_dim,
            encoder_dim=encoder_dim,
            n_layers=n_encoder_layers,
            n_heads=n_heads,
            FFN_expansion_factor=FFN_expansion_factor,
            conv_expansion_factor=conv_expansion_factor,
            input_dropout=input_dropout,
            FFN_dropout=FFN_dropout,
            attn_dropout=attn_dropout,
            conv_dropout=conv_dropout,
            kernel_size=kernel_size,
            half_step_residual=half_step_residual,
        )

        self.decoder = Decoder(
            args=args,
            num_classes=n_classes,
            d_model=decoder_dim,
            d_ff=2048,
            n_layers=6,
            n_heads=8,
            dropout_p=0.3,
            pad_id=0,
            sos_id=2001,
            eos_id=2002
        )

        self.fc = Linear(encoder_dim, n_classes, bias=False)


    def update_dropout(self, dropout_p) -> None:
        """ Update dropout probability of model """
        self.encoder.update_dropout(dropout_p)
        self.decoder.update_dropout(dropout_p)

    # todo CTC loss 일 때 쓰는듯?
    def joint(self, encoder_outputs, decoder_outputs):
        """
        encoder_outputs (torch.FloatTensor): A output sequence of encoder. `FloatTensor` of size
                ``(batch, seq_length, dimension)``
            decoder_outputs (torch.FloatTensor): A output sequence of decoder. `FloatTensor` of size
                ``(batch, seq_length, dimension)``
        Returns:
            * outputs (torch.FloatTensor): outputs of joint `encoder_outputs` and `decoder_outputs`..
        """

        if encoder_outputs.dim() == 3 and decoder_outputs.dim() == 3:
            input_length = encoder_outputs.size(1)
            target_length = decoder_outputs.size(1)

            encoder_outputs = encoder_outputs.unsqueeze(2)
            decoder_outputs = decoder_outputs.unsqueeze(1)

            encoder_outputs = encoder_outputs.repeat([1, 1, target_length, 1])
            decoder_outputs = decoder_outputs.repeat([1, input_length, 1, 1])

        # print("encoder_outputs: ", encoder_outputs.size())
        # print("decoder_outputs: ", decoder_outputs.size())
        outputs = torch.cat((encoder_outputs, decoder_outputs), dim=-1)
        outputs = self.fc(outputs)

        return outputs


    def forward(self, inputs, input_lengths, targets, target_lengths):

        # print("inputs", inputs.size())
        # print("inputs_lengths", input_lengths.size())
        # print("targets", targets.size())
        # print("target_lengths", target_lengths.size())
        encoder_outputs, encoder_output_lengths = self.encoder(inputs, input_lengths)
        # print("encoder_outputs: ", encoder_output_lengths.size())
        logits = self.decoder(
            encoder_outputs, encoder_output_lengths, targets, target_lengths, self.teacher_forcing_p
        )

        # print(logits.size())
        return logits


    # @(decorator): 감싸고 있는 함수를 호출하기전/후에 추가적으로 실행하는 기능
    @torch.no_grad()
    def decode(self, encoder_output, max_length):
        """
        Args:
            encoder_output (torch.FloatTensor): A output sequence of encoder. `FloatTensor` of size
                ``(seq_length, dimension)``
            max_length (int): max decoding time step
        Returns:
            * predicted_log_probs (torch.FloatTensor): Log probability of model predictions.
        """
        pred_tokens, hidden_state = list(), None
        decoder_input = encoder_output.new_tensor([[self.decoder.sos_id]], dtype=torch.long)

        print("max_length: ", max_length)
        for t in range(max_length):
            decoder_output, hidden_state = self.decoder(decoder_input, hidden_states=hidden_state)
            step_output = self.joint(encoder_output[t].view(-1), decoder_output.view(-1))
            step_output = step_output.softmax(dim=0)
            pred_token = step_output.argmax(dim=0) # index
            pred_token = int(pred_token.item())
            pred_tokens.append(pred_token)
            decoder_input = step_output.new_tensor([[pred_token]], dtype=torch.long)

        return torch.LongTensor(pred_tokens)


    @torch.no_grad()
    def recognize(self, inputs, input_lengths):
        """
        Args:
            inputs (torch.FloatTensor): A input sequence passed to encoder. Typically for inputs this will be a padded
                `FloatTensor` of size ``(batch, seq_length, dimension)``.
            input_lengths (torch.LongTensor): The length of input tensor. ``(batch)``
        Returns:
            * predictions (torch.FloatTensor): Result of model predictions.
        """
        outputs = list()

        encoder_outputs, output_lengths = self.encoder(inputs, input_lengths)
        max_length = encoder_outputs.size(1)

        for encoder_output in encoder_outputs:
            decoded_seq = self.decode(encoder_output, max_length)
            outputs.append(decoded_seq)

        outputs = torch.stack(outputs, dim=1).transpose(0, 1)

        return outputs
























































